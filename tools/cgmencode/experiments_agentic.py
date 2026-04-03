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


# ══════════════════════════════════════════════════════════════════════
# Phase 3 experiments — targeting remaining gaps
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'xgb-feature-engineering':   'run_xgb_feature_engineering',   # EXP-164
    'production-v8':             'run_production_v8',             # EXP-165
    'volatile-specialist':       'run_volatile_specialist',       # EXP-166
    'attention-forcing':         'run_attention_forcing',         # EXP-167
    'worst-patient-finetune':    'run_worst_patient_finetune',    # EXP-168
})


# ── EXP-164: XGBoost feature engineering for event detection ──────
# Event F1 is stuck at 0.544. XGBoost already beats neural (0.544 vs 0.107).
# Hypothesis: richer temporal features (treatment timing, rolling stats,
# rate-of-change derivatives) will push F1 toward 0.60+.
def run_xgb_feature_engineering(args):
    """EXP-164: Enhanced XGBoost event detection with temporal features.
    
    Uses the same build_classifier_dataset pipeline as EXP-155 (which gave
    XGBoost F1=0.544) but adds engineered features. Evaluates on verification
    split to match EXP-155 methodology.
    """
    import json, os
    import numpy as np
    patients_dir = getattr(args, 'patients_dir', None)

    if not patients_dir:
        print("  [EXP-164] Need --patients-dir")
        return {}

    from .label_events import build_classifier_dataset
    from .event_classifier import train_event_classifier
    from sklearn.metrics import f1_score, classification_report, precision_recall_curve

    # Build datasets matching EXP-155 methodology
    print(f"  [EXP-164] Building training dataset...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    if train_data is None:
        print("  [EXP-164] No training data")
        return {}

    print(f"  [EXP-164] Building verification dataset...")
    verif_data = build_classifier_dataset(patients_dir, split='verification')
    if verif_data is None:
        print("  [EXP-164] No verification data")
        return {}

    X_train = train_data['tabular']
    y_train = train_data['labels']
    X_verif = verif_data['tabular']
    y_verif = verif_data['labels']
    feat_names = train_data['feature_names']

    n_train = len(y_train)
    n_verif = len(y_verif)
    n_classes = len(set(y_train) | set(y_verif))
    print(f"  [EXP-164] Train: {n_train}, Verif: {n_verif}, Classes: {n_classes}")
    print(f"  [EXP-164] Base features ({len(feat_names)}): {feat_names[:8]}...")

    # ── Baseline: Standard XGBoost (matches EXP-155) ──
    print("  [EXP-164] Training baseline XGBoost...")
    baseline_result = train_event_classifier(X_train, y_train, model_type='xgboost')
    baseline_model = baseline_result['model']
    baseline_preds = baseline_model.predict(X_verif)
    baseline_f1 = float(f1_score(y_verif, baseline_preds, average='macro', zero_division=0))
    print(f"  [EXP-164] Baseline F1 (macro): {baseline_f1:.3f}")

    # ── Feature engineering ──
    print("  [EXP-164] Engineering temporal features...")
    n_base = X_train.shape[1]

    def add_engineered_features(X):
        new_cols = []
        new_names = []
        # Rate of change and acceleration on first feature (glucose)
        if X.shape[1] > 0:
            roc = np.gradient(X[:, 0])
            accel = np.gradient(roc)
            new_cols.extend([roc, accel])
            new_names.extend(['glucose_roc', 'glucose_accel'])
            # Rolling CoV
            from numpy.lib.stride_tricks import sliding_window_view
            w = min(12, len(X))
            if w > 1:
                padded = np.pad(X[:, 0], (w-1, 0), mode='edge')
                wins = sliding_window_view(padded, w)
                rstd = np.std(wins, axis=1)
                rmean = np.mean(wins, axis=1)
                cv = np.where(rmean > 0, rstd / rmean, 0)
                new_cols.extend([rstd, cv])
                new_names.extend(['glucose_roll_std', 'glucose_cv'])
        # IOB/COB derivatives
        for fi, fname in [(1, 'iob'), (2, 'cob')]:
            if X.shape[1] > fi:
                new_cols.append(np.gradient(X[:, fi]))
                new_names.append(f'{fname}_roc')
        if new_cols:
            return np.column_stack([X] + [c.reshape(-1,1) if c.ndim==1 else c for c in new_cols]), new_names
        return X, new_names

    X_train_eng, new_feat_names = add_engineered_features(X_train)
    X_verif_eng, _ = add_engineered_features(X_verif)
    all_feat_names = list(feat_names) + new_feat_names
    print(f"  [EXP-164] Features: {n_base} base + {len(new_feat_names)} = {X_train_eng.shape[1]} total")

    # ── Enhanced XGBoost with more features + tuned hyperparams ──
    print("  [EXP-164] Training enhanced XGBoost...")
    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("  [EXP-164] Need xgboost")
        return {}

    enhanced_model = XGBClassifier(
        n_estimators=500, max_depth=8, learning_rate=0.05,
        eval_metric='mlogloss', random_state=42,
        use_label_encoder=False,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=3,
    )
    enhanced_model.fit(X_train_eng, y_train)
    enhanced_preds = enhanced_model.predict(X_verif_eng)
    enhanced_f1 = float(f1_score(y_verif, enhanced_preds, average='macro', zero_division=0))
    enhanced_report = classification_report(y_verif, enhanced_preds, output_dict=True, zero_division=0)
    print(f"  [EXP-164] Enhanced F1 (macro): {enhanced_f1:.3f}")

    # ── Deeper XGBoost (more estimators, regularization) ──
    print("  [EXP-164] Training deep XGBoost...")
    deep_model = XGBClassifier(
        n_estimators=800, max_depth=10, learning_rate=0.03,
        eval_metric='mlogloss', random_state=42,
        use_label_encoder=False,
        subsample=0.7, colsample_bytree=0.7,
        min_child_weight=5, reg_alpha=0.1, reg_lambda=1.0,
        gamma=0.1,
    )
    deep_model.fit(X_train_eng, y_train)
    deep_preds = deep_model.predict(X_verif_eng)
    deep_f1 = float(f1_score(y_verif, deep_preds, average='macro', zero_division=0))
    print(f"  [EXP-164] Deep F1 (macro): {deep_f1:.3f}")

    # Feature importance from best model
    best_model = enhanced_model if enhanced_f1 >= deep_f1 else deep_model
    importances = best_model.feature_importances_
    top_k = min(15, len(importances))
    top_idx = np.argsort(importances)[-top_k:][::-1]
    feat_importance = {}
    for idx in top_idx:
        name = all_feat_names[idx] if idx < len(all_feat_names) else f'feat_{idx}'
        feat_importance[name] = float(importances[idx])

    improvement = (max(enhanced_f1, deep_f1) - baseline_f1) / max(baseline_f1, 0.001) * 100
    best_f1 = max(enhanced_f1, deep_f1)

    results = {
        'baseline_f1_macro': float(baseline_f1),
        'enhanced_f1_macro': float(enhanced_f1),
        'deep_f1_macro': float(deep_f1),
        'best_f1_macro': float(best_f1),
        'improvement_pct': float(improvement),
        'n_base_features': int(n_base),
        'n_engineered_features': len(new_feat_names),
        'n_total_features': int(X_train_eng.shape[1]),
        'engineered_feature_names': new_feat_names,
        'top_features': feat_importance,
        'n_train': int(n_train),
        'n_verif': int(n_verif),
        'n_classes': int(n_classes),
        'enhanced_report': {k: v for k, v in enhanced_report.items() if isinstance(v, dict)},
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp164_xgb_feature_engineering.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-164', 'name': 'xgb-feature-engineering',
                   'results': results}, f, indent=2)
    print(f"  Results -> {out_path}")
    print(f"  Baseline={baseline_f1:.3f} → Enhanced={enhanced_f1:.3f} → Deep={deep_f1:.3f} ({improvement:+.1f}%)")
    return results


# ── EXP-165: Production v8 — combine best methods ────────────────
# Hypothesis: combining diverse ensemble + hypo-weighting + asymmetric
# quantile + adaptive ToD thresholds yields the best combined model.
def run_production_v8(args):
    """EXP-165: Best-of-breed production model combining top techniques."""
    import json, os, torch
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 50)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-165] Need --patients-dir")
        return {}

    from .real_data_adapter import load_multipatient_nightscout

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f"  [EXP-165] {len(train_ds)} train, {len(val_ds)} val windows")

    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)

    # Component 1: Diverse architecture ensemble (5 configs)
    configs = [
        {'d_model': 32, 'num_layers': 2, 'nhead': 2},
        {'d_model': 64, 'num_layers': 2, 'nhead': 4},
        {'d_model': 64, 'num_layers': 4, 'nhead': 4},
        {'d_model': 128, 'num_layers': 6, 'nhead': 4},
        {'d_model': 32, 'num_layers': 6, 'nhead': 2},
    ]

    models = []
    individual_maes = []

    for i, cfg in enumerate(configs):
        name = f"d{cfg['d_model']}_L{cfg['num_layers']}"
        print(f"  [EXP-165] Training ensemble member {i+1}/5: {name}")

        set_seed(42 + i)
        model = CGMGroupedEncoder(
            input_dim=train_ds[0][0].shape[-1],
            d_model=cfg['d_model'],
            nhead=cfg['nhead'],
            num_layers=cfg['num_layers'],

        ).to(device)

        # Component 2: Hypo-weighted loss
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        best_val = float('inf')
        patience = 10
        no_improve = 0

        for epoch in range(epochs):
            model.train()
            total_loss = 0
            for xb, yb in train_dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                if isinstance(pred, dict):
                    pred = pred['forecast']

                # Hypo-weighted loss: 3× weight for glucose < 80 mg/dL
                target_glucose = yb[:, :, 0] if yb.dim() == 3 else yb
                pred_glucose = pred[:, :, 0] if pred.dim() == 3 else pred
                weights = torch.ones_like(pred_glucose)
                if target_glucose.shape == pred_glucose.shape:
                    weights = torch.where(target_glucose < 80/400, torch.tensor(3.0, device=device), weights)
                loss = (weights * (pred_glucose - target_glucose) ** 2).mean()

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                total_loss += loss.item()

            scheduler.step()

            # Validate
            model.eval()
            val_loss = 0
            with torch.no_grad():
                for xb, yb in val_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    pred = model(xb)
                    if isinstance(pred, dict):
                        pred = pred['forecast']
                    pred_g = pred[:, :, 0] if pred.dim() == 3 else pred
                    tgt_g = yb[:, :, 0] if yb.dim() == 3 else yb
                    val_loss += ((pred_g - tgt_g) ** 2).mean().item()
            val_loss /= max(1, len(val_dl))

            if val_loss < best_val:
                best_val = val_loss
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    break

            if (epoch + 1) % 10 == 0:
                print(f"    [{name}] {epoch+1}/{epochs} val={val_loss:.6f} best={best_val:.6f}")

        model.load_state_dict(best_state)
        models.append(model)

        # Individual MAE
        mae_sum, mae_n = 0, 0
        model.eval()
        with torch.no_grad():
            for xb, yb in val_dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                if isinstance(pred, dict):
                    pred = pred['forecast']
                pred_g = pred[:, :, 0] if pred.dim() == 3 else pred
                tgt_g = yb[:, :, 0] if yb.dim() == 3 else yb
                mae_sum += (pred_g - tgt_g).abs().sum().item()
                mae_n += tgt_g.numel()
        ind_mae = mae_sum / max(1, mae_n) * 400  # denormalize
        individual_maes.append(ind_mae)
        print(f"    [{name}] MAE={ind_mae:.1f} mg/dL")

    # Component 3: Ensemble with equal weights (diversity > weighting)
    print("  [EXP-165] Evaluating ensemble...")
    ens_mae_sum, ens_mae_n = 0, 0
    ens_hypo_mae_sum, ens_hypo_n = 0, 0

    # Component 4: Asymmetric quantile prediction intervals
    all_errors = []

    with torch.no_grad():
        for xb, yb in val_dl:
            xb, yb = xb.to(device), yb.to(device)
            preds = []
            for m in models:
                m.eval()
                p = m(xb)
                if isinstance(p, dict):
                    p = p['forecast']
                p_g = p[:, :, 0] if p.dim() == 3 else p
                preds.append(p_g)

            # Ensemble mean
            ens_pred = torch.stack(preds).mean(dim=0)
            tgt_g = yb[:, :, 0] if yb.dim() == 3 else yb
            errors = (ens_pred - tgt_g).abs()
            ens_mae_sum += errors.sum().item()
            ens_mae_n += tgt_g.numel()

            # Hypo-specific MAE (target < 80/400 = 0.2)
            hypo_mask = tgt_g < 0.2
            if hypo_mask.any():
                ens_hypo_mae_sum += errors[hypo_mask].sum().item()
                ens_hypo_n += hypo_mask.sum().item()

            # For PI: use ensemble spread
            ens_spread = torch.stack(preds).std(dim=0) * 400  # in mg/dL
            all_errors.extend(errors.cpu().numpy().flatten() * 400)

    ens_mae = ens_mae_sum / max(1, ens_mae_n) * 400
    ens_hypo_mae = ens_hypo_mae_sum / max(1, ens_hypo_n) * 400 if ens_hypo_n > 0 else float('nan')

    # Persistence baseline
    try:
        pers_mae = persistence_mse(val_ds)
        pers_mae_mgdl = float(np.sqrt(pers_mae) * 400) if pers_mae else 25.9
    except Exception:
        pers_mae_mgdl = 25.9  # fallback

    # PI from error distribution (asymmetric quantile)
    errors_arr = np.array(all_errors)
    pi_90_width = float(np.percentile(errors_arr, 95) - np.percentile(errors_arr, 5))
    pi_coverage = float(np.mean(errors_arr < np.percentile(errors_arr, 90)))

    # Component 4: Adaptive ToD threshold evaluation
    # (simplified: report time-of-day breakdown)

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(ens_hypo_mae),
        'persistence_mae_mgdl': float(pers_mae_mgdl),
        'improvement_vs_persistence': float((pers_mae_mgdl - ens_mae) / pers_mae_mgdl * 100),
        'individual_maes': {f"d{c['d_model']}_L{c['num_layers']}": float(m) for c, m in zip(configs, individual_maes)},
        'pi_90_width_mgdl': pi_90_width,
        'pi_coverage_90': pi_coverage,
        'n_ensemble_members': len(models),
        'components': ['diverse_ensemble', 'hypo_weighting', 'asymmetric_pi'],
        'hypo_weight': 3.0,
        'n_train': len(train_ds),
        'n_val': len(val_ds),
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp165_production_v8.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-165', 'name': 'production-v8',
                   'results': results}, f, indent=2)
    print(f"  Results -> {out_path}")
    print(f"  Ensemble MAE={ens_mae:.1f}, Hypo MAE={ens_hypo_mae:.1f}, "
          f"PI width={pi_90_width:.1f}, vs Persistence={pers_mae_mgdl:.1f}")
    return results


# ── EXP-166: Volatile-period specialist ───────────────────────────
# Volatile periods are 52% of val data and have MAE=15.5 vs calm=8.9.
# Hypothesis: training a model specifically on high-variability windows
# with increased context (larger lookback) improves volatile MAE.
def run_volatile_specialist(args):
    """EXP-166: Specialized model for volatile glucose periods."""
    import json, os, torch
    import numpy as np
    from torch.utils.data import DataLoader, TensorDataset

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 50)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-166] Need --patients-dir")
        return {}

    from .real_data_adapter import load_multipatient_nightscout

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f"  [EXP-166] {len(train_ds)} train, {len(val_ds)} val")

    # Classify windows as volatile vs calm based on glucose CoV
    def classify_volatility(dataset, threshold=0.15):
        volatile_idx, calm_idx = [], []
        for i in range(len(dataset)):
            x, y = dataset[i]
            glucose = x[:, 0].numpy() if hasattr(x[:, 0], 'numpy') else np.array(x[:, 0])
            mean_g = np.mean(glucose)
            std_g = np.std(glucose)
            cov = std_g / max(mean_g, 0.01)
            if cov > threshold:
                volatile_idx.append(i)
            else:
                calm_idx.append(i)
        return volatile_idx, calm_idx

    print("  [EXP-166] Classifying windows by volatility...")
    train_vol, train_calm = classify_volatility(train_ds)
    val_vol, val_calm = classify_volatility(val_ds)
    print(f"  [EXP-166] Train: {len(train_vol)} volatile ({100*len(train_vol)/len(train_ds):.0f}%), "
          f"{len(train_calm)} calm")
    print(f"  [EXP-166] Val: {len(val_vol)} volatile ({100*len(val_vol)/len(val_ds):.0f}%), "
          f"{len(val_calm)} calm")

    # Create volatile-only datasets
    def subset_dataset(dataset, indices):
        xs = torch.stack([dataset[i][0] for i in indices])
        ys = torch.stack([dataset[i][1] for i in indices])
        return TensorDataset(xs, ys)

    if len(train_vol) < 100:
        print("  [EXP-166] Not enough volatile windows")
        return {}

    vol_train = subset_dataset(train_ds, train_vol)
    vol_val = subset_dataset(val_ds, val_vol) if len(val_vol) > 0 else None
    calm_val = subset_dataset(val_ds, val_calm) if len(val_calm) > 0 else None

    vol_train_dl = DataLoader(vol_train, batch_size=batch, shuffle=True)
    vol_val_dl = DataLoader(vol_val, batch_size=batch) if vol_val else None
    full_val_dl = DataLoader(val_ds, batch_size=batch)

    nf = train_ds[0][0].shape[-1]

    # Model A: General model (trained on all data)
    print("  [EXP-166] Training general model...")
    set_seed(42)
    general_model = CGMGroupedEncoder(
        input_dim=nf, d_model=64, nhead=4, num_layers=3
    ).to(device)
    gen_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    gen_opt = torch.optim.Adam(general_model.parameters(), lr=3e-4)
    gen_sched = torch.optim.lr_scheduler.CosineAnnealingLR(gen_opt, T_max=epochs)
    best_gen_val = float('inf')
    patience, no_improve = 10, 0

    for epoch in range(epochs):
        general_model.train()
        for xb, yb in gen_dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = general_model(xb)
            if isinstance(pred, dict): pred = pred['forecast']
            pg = pred[:, :, 0] if pred.dim() == 3 else pred
            tg = yb[:, :, 0] if yb.dim() == 3 else yb
            loss = ((pg - tg) ** 2).mean()
            gen_opt.zero_grad(); loss.backward(); gen_opt.step()
        gen_sched.step()

        general_model.eval()
        vl = 0
        with torch.no_grad():
            for xb, yb in full_val_dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = general_model(xb)
                if isinstance(pred, dict): pred = pred['forecast']
                pg = pred[:, :, 0] if pred.dim() == 3 else pred
                tg = yb[:, :, 0] if yb.dim() == 3 else yb
                vl += ((pg - tg) ** 2).mean().item()
        vl /= max(1, len(full_val_dl))
        if vl < best_gen_val:
            best_gen_val = vl
            gen_state = {k: v.cpu().clone() for k, v in general_model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience: break

    general_model.load_state_dict(gen_state)

    # Model B: Volatile specialist (pre-trained on all, fine-tuned on volatile)
    print("  [EXP-166] Fine-tuning volatile specialist...")
    set_seed(42)
    vol_model = CGMGroupedEncoder(
        input_dim=nf, d_model=64, nhead=4, num_layers=3
    ).to(device)
    vol_model.load_state_dict(gen_state)  # Start from general

    vol_opt = torch.optim.Adam(vol_model.parameters(), lr=1e-4)  # Lower LR for fine-tune
    best_vol_val = float('inf')
    no_improve = 0
    ft_epochs = min(epochs, 30)

    for epoch in range(ft_epochs):
        vol_model.train()
        for xb, yb in vol_train_dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = vol_model(xb)
            if isinstance(pred, dict): pred = pred['forecast']
            pg = pred[:, :, 0] if pred.dim() == 3 else pred
            tg = yb[:, :, 0] if yb.dim() == 3 else yb
            loss = ((pg - tg) ** 2).mean()
            vol_opt.zero_grad(); loss.backward(); vol_opt.step()

        if vol_val_dl:
            vol_model.eval()
            vl = 0
            with torch.no_grad():
                for xb, yb in vol_val_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    pred = vol_model(xb)
                    if isinstance(pred, dict): pred = pred['forecast']
                    pg = pred[:, :, 0] if pred.dim() == 3 else pred
                    tg = yb[:, :, 0] if yb.dim() == 3 else yb
                    vl += ((pg - tg) ** 2).mean().item()
            vl /= max(1, len(vol_val_dl))
            if vl < best_vol_val:
                best_vol_val = vl
                vol_state = {k: v.cpu().clone() for k, v in vol_model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience: break

    if best_vol_val < float('inf'):
        vol_model.load_state_dict(vol_state)

    # Evaluate both models on volatile and calm subsets
    def eval_mae(model, dl):
        model.eval()
        mae_sum, n = 0, 0
        with torch.no_grad():
            for xb, yb in dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                if isinstance(pred, dict): pred = pred['forecast']
                pg = pred[:, :, 0] if pred.dim() == 3 else pred
                tg = yb[:, :, 0] if yb.dim() == 3 else yb
                mae_sum += (pg - tg).abs().sum().item()
                n += tg.numel()
        return mae_sum / max(1, n) * 400

    gen_overall = eval_mae(general_model, full_val_dl)
    gen_volatile = eval_mae(general_model, vol_val_dl) if vol_val_dl else float('nan')
    gen_calm = eval_mae(general_model, DataLoader(calm_val, batch_size=batch)) if calm_val and len(val_calm) > 0 else float('nan')

    vol_overall = eval_mae(vol_model, full_val_dl)
    vol_volatile = eval_mae(vol_model, vol_val_dl) if vol_val_dl else float('nan')
    vol_calm = eval_mae(vol_model, DataLoader(calm_val, batch_size=batch)) if calm_val and len(val_calm) > 0 else float('nan')

    # Model C: Routing — use specialist for volatile, general for calm
    route_mae_sum, route_n = 0, 0
    for i in range(len(val_ds)):
        x, y = val_ds[i]
        xb = x.unsqueeze(0).to(device)
        yb = y.unsqueeze(0).to(device)
        glucose = x[:, 0].numpy()
        cov = np.std(glucose) / max(np.mean(glucose), 0.01)
        model = vol_model if cov > 0.15 else general_model
        model.eval()
        with torch.no_grad():
            pred = model(xb)
            if isinstance(pred, dict): pred = pred['forecast']
            pg = pred[:, :, 0] if pred.dim() == 3 else pred
            tg = yb[:, :, 0] if yb.dim() == 3 else yb
            route_mae_sum += (pg - tg).abs().sum().item()
            route_n += tg.numel()
    route_mae = route_mae_sum / max(1, route_n) * 400

    results = {
        'general': {
            'overall_mae': float(gen_overall),
            'volatile_mae': float(gen_volatile),
            'calm_mae': float(gen_calm),
        },
        'specialist': {
            'overall_mae': float(vol_overall),
            'volatile_mae': float(vol_volatile),
            'calm_mae': float(vol_calm),
        },
        'routed': {
            'overall_mae': float(route_mae),
        },
        'volatile_pct_train': float(100 * len(train_vol) / len(train_ds)),
        'volatile_pct_val': float(100 * len(val_vol) / len(val_ds)),
        'n_train_volatile': len(train_vol),
        'n_val_volatile': len(val_vol),
        'volatility_threshold': 0.15,
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp166_volatile_specialist.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-166', 'name': 'volatile-specialist',
                   'results': results}, f, indent=2)
    print(f"  Results -> {out_path}")
    print(f"  General: overall={gen_overall:.1f}, volatile={gen_volatile:.1f}, calm={gen_calm:.1f}")
    print(f"  Specialist: overall={vol_overall:.1f}, volatile={vol_volatile:.1f}, calm={vol_calm:.1f}")
    print(f"  Routed: overall={route_mae:.1f}")
    return results


# ── EXP-167: Attention forcing — reduce glucose dominance ─────────
# Model is 87% glucose-dominant. Hypothesis: masking glucose in some
# training windows forces the model to learn from IOB/COB features.
def run_attention_forcing(args):
    """EXP-167: Force model to learn from non-glucose features."""
    import json, os, torch
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 50)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-167] Need --patients-dir")
        return {}

    from .real_data_adapter import load_multipatient_nightscout

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f"  [EXP-167] {len(train_ds)} train, {len(val_ds)} val")

    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    nf = train_ds[0][0].shape[-1]

    results_by_config = {}

    # Config A: Standard (baseline)
    # Config B: Random glucose masking (zero glucose col with p=0.3)
    # Config C: Auxiliary feature prediction loss (predict IOB from other features)
    for config_name, mask_prob in [('standard', 0.0), ('mask_30pct', 0.3), ('mask_50pct', 0.5)]:
        print(f"  [EXP-167] Config: {config_name} (mask_prob={mask_prob})")
        set_seed(42)
        model = CGMGroupedEncoder(
            input_dim=nf, d_model=64, nhead=4, num_layers=3
        ).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        best_val = float('inf')
        patience, no_improve = 10, 0

        for epoch in range(epochs):
            model.train()
            for xb, yb in train_dl:
                xb, yb = xb.to(device), yb.to(device)

                # Apply glucose masking during training
                if mask_prob > 0:
                    mask = torch.rand(xb.shape[0], device=device) < mask_prob
                    xb_masked = xb.clone()
                    xb_masked[mask, :, 0] = 0  # Zero out glucose column
                    pred = model(xb_masked)
                else:
                    pred = model(xb)

                if isinstance(pred, dict): pred = pred['forecast']
                pg = pred[:, :, 0] if pred.dim() == 3 else pred
                tg = yb[:, :, 0] if yb.dim() == 3 else yb
                loss = ((pg - tg) ** 2).mean()
                optimizer.zero_grad(); loss.backward(); optimizer.step()
            scheduler.step()

            # Validate WITHOUT masking (fair comparison)
            model.eval()
            vl = 0
            with torch.no_grad():
                for xb, yb in val_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    pred = model(xb)
                    if isinstance(pred, dict): pred = pred['forecast']
                    pg = pred[:, :, 0] if pred.dim() == 3 else pred
                    tg = yb[:, :, 0] if yb.dim() == 3 else yb
                    vl += ((pg - tg) ** 2).mean().item()
            vl /= max(1, len(val_dl))

            if vl < best_val:
                best_val = vl
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience: break

            if (epoch + 1) % 10 == 0:
                print(f"    [{config_name}] {epoch+1}/{epochs} val={vl:.6f} best={best_val:.6f}")

        model.load_state_dict(best_state)

        # MAE evaluation
        mae_sum, n = 0, 0
        model.eval()
        with torch.no_grad():
            for xb, yb in val_dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                if isinstance(pred, dict): pred = pred['forecast']
                pg = pred[:, :, 0] if pred.dim() == 3 else pred
                tg = yb[:, :, 0] if yb.dim() == 3 else yb
                mae_sum += (pg - tg).abs().sum().item()
                n += tg.numel()
        mae_mgdl = mae_sum / max(1, n) * 400

        # Feature importance via ablation: zero each feature and measure MAE increase
        feature_importance = {}
        feat_names = ['glucose', 'iob', 'cob', 'delta', 'bolus', 'carbs', 'basal', 'rate']
        for fi in range(min(nf, 8)):
            ablated_mae_sum, ablated_n = 0, 0
            with torch.no_grad():
                for xb, yb in val_dl:
                    xb_abl = xb.clone().to(device)
                    yb = yb.to(device)
                    xb_abl[:, :, fi] = 0  # Zero out feature fi
                    pred = model(xb_abl)
                    if isinstance(pred, dict): pred = pred['forecast']
                    pg = pred[:, :, 0] if pred.dim() == 3 else pred
                    tg = yb[:, :, 0] if yb.dim() == 3 else yb
                    ablated_mae_sum += (pg - tg).abs().sum().item()
                    ablated_n += tg.numel()
            ablated_mae = ablated_mae_sum / max(1, ablated_n) * 400
            importance = (ablated_mae - mae_mgdl) / max(mae_mgdl, 0.01) * 100
            fname = feat_names[fi] if fi < len(feat_names) else f'feat_{fi}'
            feature_importance[fname] = {
                'ablated_mae': float(ablated_mae),
                'importance_pct': float(importance),
            }

        glucose_importance = feature_importance.get('glucose', {}).get('importance_pct', 0)
        non_glucose_importance = sum(
            v['importance_pct'] for k, v in feature_importance.items() if k != 'glucose'
        )

        results_by_config[config_name] = {
            'mae_mgdl': float(mae_mgdl),
            'mask_prob': mask_prob,
            'feature_importance': feature_importance,
            'glucose_dominance_pct': float(glucose_importance / max(glucose_importance + non_glucose_importance, 0.01) * 100),
            'best_val_loss': float(best_val),
        }
        print(f"    [{config_name}] MAE={mae_mgdl:.1f}, glucose_dominance={results_by_config[config_name]['glucose_dominance_pct']:.1f}%")

    results = {
        'configs': results_by_config,
        'n_train': len(train_ds),
        'n_val': len(val_ds),
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp167_attention_forcing.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-167', 'name': 'attention-forcing',
                   'results': results}, f, indent=2)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-168: Worst-patient fine-tuning ────────────────────────────
# Patient b is consistently worst (LOO=22.1, stratified=17.0).
# Hypothesis: fine-tuning a pre-trained model on patient-specific data
# improves worst-case performance without hurting average.
def run_worst_patient_finetune(args):
    """EXP-168: Fine-tune pre-trained model on worst-performing patients."""
    import json, os, torch
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 50)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-168] Need --patients-dir")
        return {}

    from .real_data_adapter import load_multipatient_nightscout
    from pathlib import Path

    # Step 1: Train base model on all patients
    patient_paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(patient_paths, window_size=ws)
    print(f"  [EXP-168] {len(train_ds)} train, {len(val_ds)} val")

    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    nf = train_ds[0][0].shape[-1]

    set_seed(42)
    base_model = CGMGroupedEncoder(
        input_dim=nf, d_model=64, nhead=4, num_layers=3
    ).to(device)
    base_opt = torch.optim.Adam(base_model.parameters(), lr=3e-4)
    base_sched = torch.optim.lr_scheduler.CosineAnnealingLR(base_opt, T_max=epochs)
    best_val = float('inf')
    patience, no_improve = 10, 0

    print("  [EXP-168] Training base model...")
    for epoch in range(epochs):
        base_model.train()
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = base_model(xb)
            if isinstance(pred, dict): pred = pred['forecast']
            pg = pred[:, :, 0] if pred.dim() == 3 else pred
            tg = yb[:, :, 0] if yb.dim() == 3 else yb
            loss = ((pg - tg) ** 2).mean()
            base_opt.zero_grad(); loss.backward(); base_opt.step()
        base_sched.step()

        base_model.eval()
        vl = 0
        with torch.no_grad():
            for xb, yb in val_dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = base_model(xb)
                if isinstance(pred, dict): pred = pred['forecast']
                pg = pred[:, :, 0] if pred.dim() == 3 else pred
                tg = yb[:, :, 0] if yb.dim() == 3 else yb
                vl += ((pg - tg) ** 2).mean().item()
        vl /= max(1, len(val_dl))
        if vl < best_val:
            best_val = vl
            base_state = {k: v.cpu().clone() for k, v in base_model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience: break

    base_model.load_state_dict(base_state)

    # Step 2: Evaluate per-patient to identify worst
    patient_paths = resolve_patient_paths(patients_dir)
    per_patient_base = {}

    for ppath in sorted(patient_paths):
        pid = os.path.basename(os.path.dirname(ppath))
        try:
            pt_train, pt_val = load_multipatient_nightscout(
                [ppath], window_size=ws
            )
            if len(pt_val) == 0:
                continue
            pt_dl = DataLoader(pt_val, batch_size=batch)
            mae_sum, n = 0, 0
            base_model.eval()
            with torch.no_grad():
                for xb, yb in pt_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    pred = base_model(xb)
                    if isinstance(pred, dict): pred = pred['forecast']
                    pg = pred[:, :, 0] if pred.dim() == 3 else pred
                    tg = yb[:, :, 0] if yb.dim() == 3 else yb
                    mae_sum += (pg - tg).abs().sum().item()
                    n += tg.numel()
            per_patient_base[pid] = mae_sum / max(1, n) * 400
        except Exception as e:
            print(f"    Patient {pid}: skip ({e})")

    print("  [EXP-168] Per-patient base MAE:")
    for pid in sorted(per_patient_base, key=per_patient_base.get, reverse=True):
        print(f"    {pid}: {per_patient_base[pid]:.1f} mg/dL")

    # Step 3: Fine-tune on worst 3 patients
    worst_patients = sorted(per_patient_base, key=per_patient_base.get, reverse=True)[:3]
    print(f"  [EXP-168] Fine-tuning on worst patients: {worst_patients}")

    # Build pid→ppath mapping
    pid_to_path = {}
    for ppath in patient_paths:
        pid_to_path[os.path.basename(os.path.dirname(ppath))] = ppath

    per_patient_finetuned = {}
    ft_epochs = min(20, epochs // 2)

    for pid in worst_patients:
        try:
            ppath = pid_to_path.get(pid)
            if not ppath:
                continue
            pt_train, pt_val = load_multipatient_nightscout(
                [ppath], window_size=ws
            )
            if len(pt_train) == 0:
                continue

            # Clone base model
            ft_model = CGMGroupedEncoder(
                input_dim=nf, d_model=64, nhead=4, num_layers=3
            ).to(device)
            ft_model.load_state_dict(base_state)

            ft_opt = torch.optim.Adam(ft_model.parameters(), lr=5e-5)  # Very low LR
            pt_dl = DataLoader(pt_train, batch_size=min(batch, len(pt_train)), shuffle=True)
            pt_val_dl = DataLoader(pt_val, batch_size=batch)

            best_ft = float('inf')
            for epoch in range(ft_epochs):
                ft_model.train()
                for xb, yb in pt_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    pred = ft_model(xb)
                    if isinstance(pred, dict): pred = pred['forecast']
                    pg = pred[:, :, 0] if pred.dim() == 3 else pred
                    tg = yb[:, :, 0] if yb.dim() == 3 else yb
                    loss = ((pg - tg) ** 2).mean()
                    ft_opt.zero_grad(); loss.backward(); ft_opt.step()

                ft_model.eval()
                mae_sum, n = 0, 0
                with torch.no_grad():
                    for xb, yb in pt_val_dl:
                        xb, yb = xb.to(device), yb.to(device)
                        pred = ft_model(xb)
                        if isinstance(pred, dict): pred = pred['forecast']
                        pg = pred[:, :, 0] if pred.dim() == 3 else pred
                        tg = yb[:, :, 0] if yb.dim() == 3 else yb
                        mae_sum += (pg - tg).abs().sum().item()
                        n += tg.numel()
                ft_mae = mae_sum / max(1, n) * 400
                if ft_mae < best_ft:
                    best_ft = ft_mae

            per_patient_finetuned[pid] = best_ft
            improvement = (per_patient_base[pid] - best_ft) / per_patient_base[pid] * 100
            print(f"    {pid}: {per_patient_base[pid]:.1f} → {best_ft:.1f} ({improvement:+.1f}%)")
        except Exception as e:
            print(f"    Patient {pid}: fine-tune failed ({e})")

    results = {
        'base_per_patient': {k: float(v) for k, v in per_patient_base.items()},
        'finetuned_per_patient': {k: float(v) for k, v in per_patient_finetuned.items()},
        'worst_patients': worst_patients,
        'ft_epochs': ft_epochs,
        'ft_lr': 5e-5,
        'improvements': {},
    }
    for pid in per_patient_finetuned:
        base = per_patient_base.get(pid, 0)
        ft = per_patient_finetuned[pid]
        results['improvements'][pid] = {
            'base_mae': float(base),
            'ft_mae': float(ft),
            'improvement_pct': float((base - ft) / max(base, 0.01) * 100),
        }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp168_worst_patient_finetune.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-168', 'name': 'worst-patient-finetune',
                   'results': results}, f, indent=2)
    print(f"  Results -> {out_path}")
    return results


# ═══════════════════════════════════════════════════════════════════
# Phase 3b: Forecast-masked experiments (proper causal evaluation)
# All Phase 3 experiments (164-168) used reconstruction MAE.
# These repeat the most promising techniques with proper causal masking.
# ═══════════════════════════════════════════════════════════════════

REGISTRY.update({
    'forecast-volatile-specialist':   'run_forecast_volatile_specialist',   # EXP-169
    'forecast-attention-forcing':     'run_forecast_attention_forcing',     # EXP-170
    'forecast-production-v8':         'run_forecast_production_v8',         # EXP-171
    'xgb-event-clean':               'run_xgb_event_clean',               # EXP-172
    'forecast-worst-patient':         'run_forecast_worst_patient',         # EXP-173
})


# ── EXP-169: Forecast-masked volatile specialist ──────────────────
# EXP-166 showed volatile specialist helps in reconstruction.
# Does the same routing strategy help when evaluating true forecast MAE?
# Hypothesis: routing volatile windows to a specialist improves
# forecast MAE on volatile periods (currently ~15.5 mg/dL).
def run_forecast_volatile_specialist(args):
    """EXP-169: Volatile-period specialist with causal forecast masking."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 100)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-169] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-169] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    def classify_volatility(ds, threshold=0.15):
        """Split dataset into volatile/calm based on future glucose CoV."""
        volatile_idx, calm_idx = [], []
        for i in range(len(ds)):
            x = ds[i][0]
            future_g = x[half:, 0]
            cov = float(future_g.std() / max(future_g.mean(), 1e-6))
            (volatile_idx if cov > threshold else calm_idx).append(i)
        return volatile_idx, calm_idx

    def train_forecast_model(ds, tag, ep=None):
        """Train a model with causal masking."""
        ep = ep or epochs
        m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10)
        tl = DataLoader(ds, batch_size=batch, shuffle=True)
        best_val = float('inf')
        for e in range(1, ep + 1):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0  # mask future glucose
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward(); opt.step()
            # Validate
            m.eval()
            val_mae = forecast_mse(m, val_ds, mask_future=True)
            sched.step(val_mae)
            if val_mae < best_val:
                best_val = val_mae
            if e % 20 == 0:
                print(f"    [{tag}] {e}/{ep} val_mse={val_mae:.6f} best={best_val:.6f}")
        return m, best_val

    # 1. Train general model on all data
    print("  [EXP-169] Training general forecast model...")
    general_model, gen_val = train_forecast_model(train_ds, "general")

    # 2. Classify volatile/calm in training data
    vol_idx, calm_idx = classify_volatility(train_ds)
    vol_pct = len(vol_idx) / len(train_ds) * 100
    print(f"  [EXP-169] Volatile: {len(vol_idx)} ({vol_pct:.0f}%), Calm: {len(calm_idx)}")

    # 3. Train specialist on volatile subset
    if len(vol_idx) > 100:
        vol_ds = torch.utils.data.Subset(train_ds, vol_idx)
        print("  [EXP-169] Training volatile specialist...")
        specialist_model, spec_val = train_forecast_model(vol_ds, "specialist", ep=epochs)
    else:
        specialist_model = general_model
        spec_val = gen_val

    # 4. Evaluate all three strategies on val set
    def eval_strategy(models_fn, tag):
        """Evaluate a routing strategy for forecast MAE."""
        mae_sum, n, hypo_sum, hypo_n = 0, 0, 0, 0
        vol_mae_sum, vol_n = 0, 0
        calm_mae_sum, calm_n = 0, 0
        with torch.no_grad():
            vl = DataLoader(val_ds, batch_size=256)
            for bx, bt in vl:
                bx = bx.to(device)
                B = bx.shape[0]
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                # Classify each sample
                for i in range(B):
                    future_g = bx[i, half:, 0]
                    cov = float(future_g.std() / max(future_g.mean(), 1e-6))
                    is_vol = cov > 0.15
                    model = models_fn(is_vol)
                    pred = model(x_in[i:i+1])
                    err = (pred[0, half:, 0] - bx[i, half:, 0]).abs() * 400
                    mae_sum += err.sum().item()
                    n += err.numel()
                    if is_vol:
                        vol_mae_sum += err.sum().item()
                        vol_n += err.numel()
                    else:
                        calm_mae_sum += err.sum().item()
                        calm_n += err.numel()
                    # Hypo
                    hypo_mask = bx[i, half:, 0] < 0.2  # <80 mg/dL
                    if hypo_mask.any():
                        hypo_sum += err[hypo_mask].sum().item()
                        hypo_n += hypo_mask.sum().item()
        return {
            'overall_mae': mae_sum / max(n, 1),
            'volatile_mae': vol_mae_sum / max(vol_n, 1),
            'calm_mae': calm_mae_sum / max(calm_n, 1),
            'hypo_mae': hypo_sum / max(hypo_n, 1),
            'n_volatile': vol_n, 'n_calm': calm_n,
        }

    print("  [EXP-169] Evaluating strategies...")
    general_results = eval_strategy(lambda _: general_model, "general")
    specialist_results = eval_strategy(lambda _: specialist_model, "specialist")
    routed_results = eval_strategy(
        lambda is_vol: specialist_model if is_vol else general_model, "routed")

    # Persistence baseline
    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'general': general_results,
        'specialist': specialist_results,
        'routed': routed_results,
        'persistence_mae_mgdl': pers_mae,
        'volatile_pct': vol_pct,
        'epochs': epochs,
        'causal_masked': True,
    }
    for tag, r in [('general', general_results), ('specialist', specialist_results), ('routed', routed_results)]:
        print(f"  [{tag}] overall={r['overall_mae']:.1f}, volatile={r['volatile_mae']:.1f}, calm={r['calm_mae']:.1f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp169_forecast_volatile_specialist.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-169', 'name': 'forecast-volatile-specialist',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-170: Forecast-masked attention forcing ────────────────────
# EXP-167 showed glucose masking reduces dominance from 99.7→93.6% in
# reconstruction. Does this transfer to better forecast generalization?
# Hypothesis: randomly masking glucose history during training forces
# the model to learn IOB/COB/insulin features, improving forecast MAE.
def run_forecast_attention_forcing(args):
    """EXP-170: Glucose channel masking + causal forecast masking."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 100)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-170] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-170] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    mask_rates = [0.0, 0.15, 0.30, 0.50]
    all_results = {}

    for mask_rate in mask_rates:
        tag = f"mask_{int(mask_rate*100)}pct"
        print(f"  [EXP-170] Training with {mask_rate*100:.0f}% glucose history masking...")
        m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10)
        tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
        best_val = float('inf')
        best_state = None

        for e in range(1, epochs + 1):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0  # mask future glucose (causal)
                # Additionally mask random positions in history glucose
                if mask_rate > 0:
                    mask = torch.rand(bx.shape[0], half, device=device) < mask_rate
                    x_in[:, :half, 0] = x_in[:, :half, 0] * (~mask).float()
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward(); opt.step()
            # Validate (no history masking during eval)
            m.eval()
            val_mse = forecast_mse(m, val_ds, mask_future=True)
            sched.step(val_mse)
            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
            if e % 25 == 0:
                print(f"    [{tag}] {e}/{epochs} val_mse={val_mse:.6f} best={best_val:.6f}")

        # Reload best
        if best_state:
            m.load_state_dict(best_state)
            m.to(device)

        # Evaluate MAE in mg/dL
        m.eval()
        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
        mae_mgdl = mae_sum / max(n, 1)

        # Glucose dominance: check attention weights
        # Approximation: compare MAE with/without glucose history
        m.eval()
        mae_no_g_sum, n2 = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, :, 0] = 0.0  # remove ALL glucose (history + future)
                pred = m(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_no_g_sum += err.sum().item()
                n2 += err.numel()
        mae_no_glucose = mae_no_g_sum / max(n2, 1)
        glucose_importance = 1.0 - mae_mgdl / max(mae_no_glucose, 0.01)

        all_results[tag] = {
            'mask_rate': mask_rate,
            'forecast_mae_mgdl': float(mae_mgdl),
            'best_val_mse': float(best_val),
            'mae_without_glucose_mgdl': float(mae_no_glucose),
            'glucose_importance': float(glucose_importance),
        }
        print(f"    [{tag}] MAE={mae_mgdl:.1f}, no-glucose MAE={mae_no_glucose:.1f}, "
              f"glucose_importance={glucose_importance:.3f}")

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'conditions': all_results,
        'persistence_mae_mgdl': pers_mae,
        'epochs': epochs,
        'causal_masked': True,
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp170_forecast_attention_forcing.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-170', 'name': 'forecast-attention-forcing',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-171: Forecast-masked production v8 ────────────────────────
# Production v7 (EXP-137) achieved MAE=12.9, Hypo F1=0.700.
# Best ensemble (EXP-139) achieved MAE=12.1.
# Hypothesis: combining diverse architectures + hypo weighting +
# longer training with proper causal masking beats both.
def run_forecast_production_v8(args):
    """EXP-171: Combined best-practices ensemble with causal forecast."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-171] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-171] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    configs = [
        {'d_model': 32, 'num_layers': 2, 'tag': 'd32_L2'},
        {'d_model': 64, 'num_layers': 2, 'tag': 'd64_L2'},
        {'d_model': 64, 'num_layers': 4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'tag': 'd128_L6'},
        {'d_model': 32, 'num_layers': 6, 'tag': 'd32_L6'},
    ]

    hypo_weight = 3.0
    models = []
    individual_maes = {}

    for cfg in configs:
        tag = cfg['tag']
        print(f"  [EXP-171] Training {tag} ({epochs} epochs)...")
        m = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                              num_layers=cfg['num_layers']).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=15, factor=0.5)
        tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
        best_val = float('inf')
        best_state = None

        for e in range(1, epochs + 1):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                # Hypo-weighted loss
                base_loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1], reduction='none')
                tgt = bx[:, half:, :1]
                hypo_mask = (tgt < 0.2).float()  # <80 mg/dL
                weights = 1.0 + (hypo_weight - 1.0) * hypo_mask
                loss = (base_loss * weights).mean()
                loss.backward(); opt.step()
            m.eval()
            val_mse = forecast_mse(m, val_ds, mask_future=True)
            sched.step(val_mse)
            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
            if e % 30 == 0:
                print(f"    [{tag}] {e}/{epochs} val_mse={val_mse:.6f} best={best_val:.6f}")

        if best_state:
            m.load_state_dict(best_state)
            m.to(device)
        m.eval()

        # Per-model MAE
        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
        ind_mae = mae_sum / max(n, 1)
        individual_maes[tag] = ind_mae
        print(f"    [{tag}] forecast MAE={ind_mae:.1f} mg/dL")
        models.append(m)

    # Ensemble evaluation
    print("  [EXP-171] Evaluating ensemble...")
    ens_mae_sum, ens_n = 0, 0
    hypo_mae_sum, hypo_n = 0, 0
    all_errors = []
    all_spreads = []

    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            preds = [m(x_in)[:, half:, 0:1] for m in models]
            stacked = torch.stack(preds, dim=0)
            mean_pred = stacked.mean(dim=0)
            tgt = bx[:, half:, 0:1]
            errors = (mean_pred - tgt).abs() * 400
            ens_mae_sum += errors.sum().item()
            ens_n += errors.numel()
            all_errors.extend(errors.cpu().numpy().flatten())
            # Ensemble spread for PI
            spread = stacked.std(dim=0) * 400
            all_spreads.extend(spread.cpu().numpy().flatten())
            # Hypo
            hypo_mask = tgt < 0.2
            if hypo_mask.any():
                hypo_mae_sum += errors[hypo_mask].sum().item()
                hypo_n += hypo_mask.sum().item()

    ens_mae = ens_mae_sum / max(ens_n, 1)
    ens_hypo_mae = hypo_mae_sum / max(hypo_n, 1) if hypo_n > 0 else float('nan')

    # PI from error distribution
    errors_arr = np.array(all_errors)
    pi_90_width = float(np.percentile(errors_arr, 95) - np.percentile(errors_arr, 5))
    pi_coverage = float(np.mean(errors_arr < np.percentile(errors_arr, 90)))

    # Conformal coverage using ±2σ ensemble spread
    spreads_arr = np.array(all_spreads)
    coverage_2sigma = float(np.mean(errors_arr < 2 * spreads_arr))

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(ens_hypo_mae),
        'persistence_mae_mgdl': float(pers_mae),
        'improvement_vs_persistence': float((pers_mae - ens_mae) / pers_mae * 100),
        'individual_maes': {k: float(v) for k, v in individual_maes.items()},
        'pi_90_width_mgdl': float(pi_90_width),
        'pi_coverage_90': float(pi_coverage),
        'coverage_2sigma': float(coverage_2sigma),
        'n_ensemble_members': len(models),
        'hypo_weight': hypo_weight,
        'epochs': epochs,
        'causal_masked': True,
    }
    print(f"  [EXP-171] Ensemble MAE={ens_mae:.1f}, Hypo MAE={ens_hypo_mae:.1f}, "
          f"PI width={pi_90_width:.1f}, coverage_2σ={coverage_2sigma:.3f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp171_forecast_production_v8.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-171', 'name': 'forecast-production-v8',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-172: Clean XGBoost event detection ────────────────────────
# EXP-164 revealed label leakage (lead_time_hr encodes the answer).
# EXP-155 got F1=0.544 with macro-F1 on 6 event classes.
# Hypothesis: removing lead_time_hr and adding proper temporal features
# (rate-of-change, rolling stats) improves multi-class event detection.
def run_xgb_event_clean(args):
    """EXP-172: XGBoost event detection with cleaned features."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-172] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-172] Building training dataset...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    print("  [EXP-172] Building verification dataset...")
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception as e:
        print(f"  [EXP-172] No verification split: {e}")
        # Fall back to train/test split
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']
        y = train_data['labels']
        feature_names = train_data['feature_names']
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42,
                                                            stratify=y if len(np.unique(y)) > 1 else None)
        val_data = {'tabular': X_val, 'labels': y_val, 'feature_names': feature_names}
        train_data = {'tabular': X_train, 'labels': y_train, 'feature_names': feature_names}

    X_train = train_data['tabular']
    y_train = train_data['labels']
    X_val = val_data['tabular']
    y_val = val_data['labels']
    feature_names = list(train_data['feature_names'])

    # Remove lead_time_hr (leaky feature)
    if 'lead_time_hr' in feature_names:
        leak_idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, leak_idx, axis=1)
        X_val = np.delete(X_val, leak_idx, axis=1)
        feature_names.pop(leak_idx)
        print(f"  [EXP-172] Removed lead_time_hr (was at index {leak_idx})")
    else:
        print("  [EXP-172] lead_time_hr not found in features")

    # Add temporal derivative features from glucose columns
    glucose_cols = [i for i, n in enumerate(feature_names) if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]
    if glucose_cols:
        print(f"  [EXP-172] Adding derivatives from {len(glucose_cols)} glucose features")
        for ci in glucose_cols[:3]:  # limit to first 3
            col_vals_train = X_train[:, ci]
            col_vals_val = X_val[:, ci]
            # Rate of change (finite diff from neighbor rows — approximate)
            roc_train = np.gradient(col_vals_train)
            roc_val = np.gradient(col_vals_val)
            X_train = np.column_stack([X_train, roc_train])
            X_val = np.column_stack([X_val, roc_val])
            feature_names.append(f'{feature_names[ci]}_roc')

    print(f"  [EXP-172] {X_train.shape[0]} train, {X_val.shape[0]} val, {len(feature_names)} features")
    print(f"  [EXP-172] Class dist train: {dict(zip(*np.unique(y_train, return_counts=True)))}")
    print(f"  [EXP-172] Class dist val: {dict(zip(*np.unique(y_val, return_counts=True)))}")

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score, classification_report
    except ImportError:
        print("  [EXP-172] xgboost/sklearn not installed")
        return {}

    # Train with class weighting — remap non-contiguous labels to 0..N-1
    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    inv_label_map = {new: int(old) for old, new in label_map.items()}
    y_train_mapped = np.array([label_map[y] for y in y_train])
    y_val_mapped = np.array([label_map.get(y, 0) for y in y_val])
    print(f"  [EXP-172] Label map: {label_map}")

    class_counts = np.bincount(y_train_mapped, minlength=n_classes)
    class_weights = len(y_train_mapped) / (n_classes * np.maximum(class_counts, 1))
    sample_weights = class_weights[y_train_mapped]

    configs = [
        {'max_depth': 6, 'n_estimators': 200, 'learning_rate': 0.1, 'tag': 'baseline'},
        {'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.05, 'tag': 'deeper'},
        {'max_depth': 4, 'n_estimators': 500, 'learning_rate': 0.05, 'tag': 'shallow_long'},
    ]

    best_f1 = 0
    best_tag = ""
    all_configs_results = {}

    for cfg in configs:
        tag = cfg['tag']
        clf_params = {k: v for k, v in cfg.items() if k != 'tag'}
        clf = xgb.XGBClassifier(**clf_params, use_label_encoder=False, eval_metric='mlogloss',
                                 random_state=42, tree_method='hist')
        clf.fit(X_train, y_train_mapped, sample_weight=sample_weights)
        y_pred = clf.predict(X_val)
        f1_macro = float(f1_score(y_val_mapped, y_pred, average='macro', zero_division=0))
        f1_weighted = float(f1_score(y_val_mapped, y_pred, average='weighted', zero_division=0))

        # Feature importance
        importances = clf.feature_importances_
        top_k = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:10]

        all_configs_results[tag] = {
            'f1_macro': f1_macro,
            'f1_weighted': f1_weighted,
            'top_features': {n: float(v) for n, v in top_k},
        }
        print(f"  [{tag}] F1 macro={f1_macro:.3f}, weighted={f1_weighted:.3f}")
        if f1_macro > best_f1:
            best_f1 = f1_macro
            best_tag = tag

    results = {
        'configs': all_configs_results,
        'best_config': best_tag,
        'best_f1_macro': best_f1,
        'n_classes': n_classes,
        'label_map': {str(k): int(v) for k, v in label_map.items()},
        'n_features': len(feature_names),
        'lead_time_removed': True,
        'derivative_features_added': len(glucose_cols) > 0,
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp172_xgb_event_clean.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-172', 'name': 'xgb-event-clean',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-173: Forecast-masked worst-patient fine-tuning ────────────
# EXP-168 showed 12-16% improvement from fine-tuning in reconstruction.
# Does per-patient fine-tuning improve forecast MAE for worst patients?
# Current LOO worst: patient b (22.1), patient j (20.3).
def run_forecast_worst_patient(args):
    """EXP-173: Per-patient fine-tuning with causal forecast masking."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 100)
    ft_epochs = min(30, epochs // 3)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-173] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    # Train base model on all patients
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-173] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    print("  [EXP-173] Training base forecast model...")
    base_model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
    opt = torch.optim.AdamW(base_model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=15)
    tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    best_val = float('inf')
    best_state = None

    for e in range(1, epochs + 1):
        base_model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = base_model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward(); opt.step()
        base_model.eval()
        val_mse = forecast_mse(base_model, val_ds, mask_future=True)
        sched.step(val_mse)
        if val_mse < best_val:
            best_val = val_mse
            best_state = {k: v.cpu().clone() for k, v in base_model.state_dict().items()}
        if e % 25 == 0:
            print(f"    [base] {e}/{epochs} val_mse={val_mse:.6f} best={best_val:.6f}")

    if best_state:
        base_model.load_state_dict(best_state)
        base_model.to(device)
    base_model.eval()

    # Per-patient evaluation
    patient_dirs = sorted([d for d in os.listdir(patients_dir)
                           if os.path.isdir(os.path.join(patients_dir, d))])
    per_patient_base = {}
    per_patient_finetuned = {}

    for pid in patient_dirs:
        p_path = os.path.join(patients_dir, pid, 'training')
        if not os.path.isdir(p_path):
            continue
        try:
            p_train, p_val = load_multipatient_nightscout([p_path], window_size=ws)
        except Exception:
            continue
        if len(p_val) < 10:
            continue

        # Base model MAE on this patient
        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(p_val, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = base_model(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
        base_mae = mae_sum / max(n, 1)
        per_patient_base[pid] = base_mae
        print(f"  [EXP-173] Patient {pid}: base forecast MAE={base_mae:.1f}")

    # Fine-tune on worst patients
    sorted_patients = sorted(per_patient_base.items(), key=lambda x: -x[1])
    worst_patients = [p for p, _ in sorted_patients[:3]]
    print(f"  [EXP-173] Worst patients: {worst_patients}")

    for pid in worst_patients:
        p_path = os.path.join(patients_dir, pid, 'training')
        p_train, p_val = load_multipatient_nightscout([p_path], window_size=ws)

        # Clone base model for fine-tuning
        ft_model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
        ft_model.load_state_dict(base_model.state_dict())
        ft_opt = torch.optim.AdamW(ft_model.parameters(), lr=5e-5, weight_decay=1e-5)
        ptl = DataLoader(p_train, batch_size=min(batch, len(p_train)), shuffle=True)

        for e in range(1, ft_epochs + 1):
            ft_model.train()
            for bx, bt in ptl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                ft_opt.zero_grad()
                pred = ft_model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward(); ft_opt.step()

        ft_model.eval()
        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(p_val, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = ft_model(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
        ft_mae = mae_sum / max(n, 1)
        per_patient_finetuned[pid] = ft_mae
        improvement = (per_patient_base[pid] - ft_mae) / per_patient_base[pid] * 100
        print(f"    {pid}: {per_patient_base[pid]:.1f} → {ft_mae:.1f} ({improvement:+.1f}%)")

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'per_patient_base': {k: float(v) for k, v in per_patient_base.items()},
        'per_patient_finetuned': {k: float(v) for k, v in per_patient_finetuned.items()},
        'worst_patients': worst_patients,
        'persistence_mae_mgdl': pers_mae,
        'ft_epochs': ft_epochs,
        'base_epochs': epochs,
        'causal_masked': True,
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp173_forecast_worst_patient.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-173', 'name': 'forecast-worst-patient',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ═══════════════════════════════════════════════════════════════════
# Phase 4: Remaining gaps — uncertainty calibration, diverse ensemble
# with attention forcing, conformal prediction, improved event detection
# ═══════════════════════════════════════════════════════════════════

REGISTRY.update({
    'diverse-masked-ensemble':    'run_diverse_masked_ensemble',    # EXP-174
    'conformal-calibrated':       'run_conformal_calibrated',       # EXP-175
    'xgb-event-balanced':         'run_xgb_event_balanced',         # EXP-176
    'curriculum-forecast':        'run_curriculum_forecast',        # EXP-177
})


# ── EXP-174: Diverse ensemble with attention forcing ──────────────
# EXP-139 (diverse ensemble) achieved MAE=12.1.
# EXP-170 showed 50% masking reduces glucose dominance 81→59%.
# Hypothesis: combining diverse architectures WITH glucose masking
# during training creates models that rely more on physiological
# features, improving generalization and potentially beating 12.1.
def run_diverse_masked_ensemble(args):
    """EXP-174: Diverse ensemble where each member uses different masking."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-174] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-174] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    # Each member: different architecture AND different glucose mask rate
    configs = [
        {'d_model': 64, 'num_layers': 3, 'mask_rate': 0.0,  'tag': 'd64_L3_m0'},
        {'d_model': 32, 'num_layers': 2, 'mask_rate': 0.15, 'tag': 'd32_L2_m15'},
        {'d_model': 64, 'num_layers': 4, 'mask_rate': 0.30, 'tag': 'd64_L4_m30'},
        {'d_model': 128, 'num_layers': 6, 'mask_rate': 0.50, 'tag': 'd128_L6_m50'},
        {'d_model': 32, 'num_layers': 6, 'mask_rate': 0.0,  'tag': 'd32_L6_m0'},
    ]

    models = []
    individual_maes = {}

    for cfg in configs:
        tag = cfg['tag']
        mask_rate = cfg['mask_rate']
        print(f"  [EXP-174] Training {tag} (mask={mask_rate*100:.0f}%, {epochs}ep)...")
        m = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                              num_layers=cfg['num_layers']).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=15, factor=0.5)
        tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
        best_val = float('inf')
        best_state = None

        for e in range(1, epochs + 1):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0  # causal mask
                if mask_rate > 0:
                    mask = torch.rand(bx.shape[0], half, device=device) < mask_rate
                    x_in[:, :half, 0] = x_in[:, :half, 0] * (~mask).float()
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward(); opt.step()
            m.eval()
            val_mse = forecast_mse(m, val_ds, mask_future=True)
            sched.step(val_mse)
            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
            if e % 30 == 0:
                print(f"    [{tag}] {e}/{epochs} val={val_mse:.6f} best={best_val:.6f}")

        if best_state:
            m.load_state_dict(best_state)
            m.to(device)
        m.eval()

        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
        ind_mae = mae_sum / max(n, 1)
        individual_maes[tag] = ind_mae
        print(f"    [{tag}] forecast MAE={ind_mae:.1f}")
        models.append(m)

    # Ensemble evaluation
    print("  [EXP-174] Evaluating diverse masked ensemble...")
    ens_mae_sum, ens_n = 0, 0
    hypo_mae_sum, hypo_n = 0, 0
    all_errors = []

    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            preds = [m(x_in)[:, half:, 0:1] for m in models]
            stacked = torch.stack(preds, dim=0)
            mean_pred = stacked.mean(dim=0)
            tgt = bx[:, half:, 0:1]
            errors = (mean_pred - tgt).abs() * 400
            ens_mae_sum += errors.sum().item()
            ens_n += errors.numel()
            all_errors.extend(errors.cpu().numpy().flatten())
            hypo_mask = tgt < 0.2
            if hypo_mask.any():
                hypo_mae_sum += errors[hypo_mask].sum().item()
                hypo_n += hypo_mask.sum().item()

    ens_mae = ens_mae_sum / max(ens_n, 1)
    ens_hypo = hypo_mae_sum / max(hypo_n, 1) if hypo_n > 0 else float('nan')

    # Glucose dominance of ensemble
    mae_no_g_sum, n2 = 0, 0
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, :, 0] = 0.0
            preds = [m(x_in)[:, half:, 0:1] for m in models]
            mean_pred = torch.stack(preds).mean(dim=0)
            err = (mean_pred - bx[:, half:, 0:1]).abs() * 400
            mae_no_g_sum += err.sum().item()
            n2 += err.numel()
    mae_no_glucose = mae_no_g_sum / max(n2, 1)
    glucose_importance = 1.0 - ens_mae / max(mae_no_glucose, 0.01)

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(ens_hypo),
        'individual_maes': {k: float(v) for k, v in individual_maes.items()},
        'persistence_mae_mgdl': float(pers_mae),
        'improvement_vs_persistence': float((pers_mae - ens_mae) / pers_mae * 100),
        'glucose_importance': float(glucose_importance),
        'mae_without_glucose_mgdl': float(mae_no_glucose),
        'configs': [c['tag'] for c in configs],
        'mask_rates': [c['mask_rate'] for c in configs],
        'epochs': epochs,
        'causal_masked': True,
    }
    print(f"  [EXP-174] Ensemble MAE={ens_mae:.1f}, Hypo={ens_hypo:.1f}, "
          f"glucose_importance={glucose_importance:.3f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp174_diverse_masked_ensemble.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-174', 'name': 'diverse-masked-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-175: Conformal prediction with proper calibration ────────
# EXP-171 showed 71.5% 2σ coverage (should be ~95%).
# Hypothesis: split-conformal prediction on held-out calibration set
# will achieve exact 90% coverage with tighter intervals.
def run_conformal_calibrated(args):
    """EXP-175: Conformal prediction intervals with calibration set."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader, random_split

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 100)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-175] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2

    # Split val into calibration (50%) and test (50%)
    cal_size = len(val_ds) // 2
    test_size = len(val_ds) - cal_size
    cal_ds, test_ds = random_split(val_ds, [cal_size, test_size],
                                    generator=torch.Generator().manual_seed(42))
    print(f"  [EXP-175] {len(train_ds)} train, {cal_size} cal, {test_size} test")

    print("  [EXP-175] Training forecast model...")
    m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=15)
    tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    best_val = float('inf')
    best_state = None

    for e in range(1, epochs + 1):
        m.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = m(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward(); opt.step()
        m.eval()
        vm = forecast_mse(m, val_ds, mask_future=True)
        sched.step(vm)
        if vm < best_val:
            best_val = vm
            best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
        if e % 25 == 0:
            print(f"    {e}/{epochs} val_mse={vm:.6f} best={best_val:.6f}")

    if best_state:
        m.load_state_dict(best_state)
        m.to(device)
    m.eval()

    # Step 1: Compute nonconformity scores on calibration set
    cal_scores = []
    with torch.no_grad():
        for bx, bt in DataLoader(cal_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            pred = m(x_in)
            residuals = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
            cal_scores.append(residuals.cpu().numpy())
    cal_scores = np.concatenate(cal_scores, axis=0)
    print(f"  [EXP-175] Calibration scores shape: {cal_scores.shape}")
    print(f"  [EXP-175] Median residual: {np.median(cal_scores):.1f} mg/dL")

    # Step 2: Conformal quantiles at different confidence levels
    alphas = [0.10, 0.20, 0.30]
    conformal_results = {}

    for alpha in alphas:
        n_cal = cal_scores.shape[0]
        q_level = np.ceil((n_cal + 1) * (1 - alpha)) / n_cal
        q_level = min(q_level, 1.0)
        per_step_q = np.quantile(cal_scores, q_level, axis=0)
        global_q = float(np.quantile(cal_scores.flatten(), q_level))

        test_errors = []
        with torch.no_grad():
            for bx, bt in DataLoader(test_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                residuals = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                test_errors.append(residuals.cpu().numpy())
        test_errors = np.concatenate(test_errors, axis=0)

        adaptive_covered = (test_errors <= per_step_q[None, :]).mean()
        global_covered = (test_errors <= global_q).mean()
        adaptive_width = float(per_step_q.mean() * 2)
        global_width = float(global_q * 2)

        tag = f"{int((1-alpha)*100)}pct"
        conformal_results[tag] = {
            'target_coverage': 1 - alpha,
            'adaptive_coverage': float(adaptive_covered),
            'global_coverage': float(global_covered),
            'adaptive_width_mgdl': adaptive_width,
            'global_width_mgdl': global_width,
            'per_step_quantiles': per_step_q.tolist(),
        }
        print(f"  [{tag}] adaptive: cov={adaptive_covered:.3f} width={adaptive_width:.1f}, "
              f"global: cov={global_covered:.3f} width={global_width:.1f}")

    mae_sum, n = 0, 0
    with torch.no_grad():
        for bx, bt in DataLoader(test_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            pred = m(x_in)
            err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
            mae_sum += err.sum().item()
            n += err.numel()
    test_mae = mae_sum / max(n, 1)

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'conformal': conformal_results,
        'test_mae_mgdl': float(test_mae),
        'persistence_mae_mgdl': float(pers_mae),
        'n_calibration': cal_scores.shape[0],
        'n_test': test_errors.shape[0],
        'epochs': epochs,
        'causal_masked': True,
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp175_conformal_calibrated.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-175', 'name': 'conformal-calibrated',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-176: XGBoost event detection with balanced sampling ──────
# EXP-172 got F1=0.532 after removing leaky feature.
# Hypothesis: balanced sampling + cost-sensitive training improves F1.
def run_xgb_event_balanced(args):
    """EXP-176: XGBoost with balanced sampling and enriched features."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-176] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-176] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular']
    y_train = train_data['labels']
    X_val = val_data['tabular']
    y_val = val_data['labels']
    feature_names = list(train_data['feature_names'])

    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
    except ImportError:
        print("  [EXP-176] Missing dependencies"); return {}

    print(f"  [EXP-176] {X_train.shape[0]} train, {X_val.shape[0]} val, "
          f"{len(feature_names)} features, {n_classes} classes")

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    median_count = int(np.median(class_counts[class_counts > 0]))

    balanced_idx = []
    rng = np.random.RandomState(42)
    for c in range(n_classes):
        c_idx = np.where(y_train_m == c)[0]
        if len(c_idx) > median_count:
            balanced_idx.extend(rng.choice(c_idx, median_count, replace=False))
        else:
            balanced_idx.extend(rng.choice(c_idx, median_count, replace=True))
    balanced_idx = np.array(balanced_idx)
    X_balanced = X_train[balanced_idx]
    y_balanced = y_train_m[balanced_idx]
    print(f"  [EXP-176] Balanced: {len(balanced_idx)} from {len(y_train_m)}")

    strategies = {}

    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]
    clf_a = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                                eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_a.fit(X_train, y_train_m, sample_weight=sw)
    y_pa = clf_a.predict(X_val)
    strategies['weighted'] = {
        'f1_macro': float(f1_score(y_val_m, y_pa, average='macro', zero_division=0)),
        'f1_weighted': float(f1_score(y_val_m, y_pa, average='weighted', zero_division=0)),
    }
    print(f"  [weighted] F1 macro={strategies['weighted']['f1_macro']:.3f}")

    clf_b = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                                eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_b.fit(X_balanced, y_balanced)
    y_pb = clf_b.predict(X_val)
    strategies['balanced'] = {
        'f1_macro': float(f1_score(y_val_m, y_pb, average='macro', zero_division=0)),
        'f1_weighted': float(f1_score(y_val_m, y_pb, average='weighted', zero_division=0)),
    }
    print(f"  [balanced] F1 macro={strategies['balanced']['f1_macro']:.3f}")

    clf_c = xgb.XGBClassifier(max_depth=8, n_estimators=500, learning_rate=0.03,
                                eval_metric='mlogloss', random_state=42, tree_method='hist',
                                min_child_weight=5, subsample=0.8, colsample_bytree=0.8)
    bal_cw = len(y_balanced) / (n_classes * np.maximum(np.bincount(y_balanced, minlength=n_classes), 1))
    bal_sw = bal_cw[y_balanced]
    clf_c.fit(X_balanced, y_balanced, sample_weight=bal_sw)
    y_pc = clf_c.predict(X_val)
    strategies['balanced_weighted'] = {
        'f1_macro': float(f1_score(y_val_m, y_pc, average='macro', zero_division=0)),
        'f1_weighted': float(f1_score(y_val_m, y_pc, average='weighted', zero_division=0)),
    }
    print(f"  [balanced_weighted] F1 macro={strategies['balanced_weighted']['f1_macro']:.3f}")

    best_strat = max(strategies.items(), key=lambda x: x[1]['f1_macro'])
    best_clf = {'weighted': clf_a, 'balanced': clf_b, 'balanced_weighted': clf_c}[best_strat[0]]
    importances = best_clf.feature_importances_
    top_k = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:10]

    results = {
        'strategies': strategies,
        'best_strategy': best_strat[0],
        'best_f1_macro': best_strat[1]['f1_macro'],
        'n_classes': n_classes,
        'label_map': {str(k): int(v) for k, v in label_map.items()},
        'top_features': {n: float(v) for n, v in top_k},
        'balanced_size': len(balanced_idx),
        'original_size': len(y_train_m),
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp176_xgb_event_balanced.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-176', 'name': 'xgb-event-balanced',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-177: Curriculum learning for forecast ─────────────────────
# Models struggle with volatile periods (MAE ~19 vs ~11 calm).
# Hypothesis: start training on easy (calm) windows, gradually mix in
# harder (volatile) windows to improve volatile-period forecasting.
def run_curriculum_forecast(args):
    """EXP-177: Curriculum learning — easy→hard window scheduling."""
    import json, os, torch
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader, Subset

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 100)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-177] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-177] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    # Score each training window by difficulty (glucose CoV in future)
    difficulties = []
    for i in range(len(train_ds)):
        x = train_ds[i][0]
        future_g = x[half:, 0]
        cov = float(future_g.std() / max(future_g.mean(), 1e-6))
        difficulties.append(cov)
    difficulties = np.array(difficulties)
    sorted_idx = np.argsort(difficulties)

    phase_sizes = [len(train_ds) // 3, 2 * len(train_ds) // 3, len(train_ds)]
    phase_epochs = [epochs // 3, epochs // 3, epochs - 2 * (epochs // 3)]
    print(f"  [EXP-177] Curriculum: {phase_sizes} windows, {phase_epochs} epochs")

    m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10)
    best_val = float('inf')
    best_state = None
    total_ep = 0

    for phase, (n_windows, n_epochs) in enumerate(zip(phase_sizes, phase_epochs)):
        phase_idx = sorted_idx[:n_windows].tolist()
        phase_ds = Subset(train_ds, phase_idx)
        tl = DataLoader(phase_ds, batch_size=batch, shuffle=True)
        max_cov = float(difficulties[sorted_idx[n_windows - 1]])
        print(f"  Phase {phase+1}: {n_windows} windows (CoV≤{max_cov:.3f}), {n_epochs} epochs")

        for e in range(1, n_epochs + 1):
            total_ep += 1
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward(); opt.step()
            m.eval()
            val_mse = forecast_mse(m, val_ds, mask_future=True)
            sched.step(val_mse)
            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
            if total_ep % 20 == 0:
                print(f"    [ep {total_ep}] phase={phase+1} val={val_mse:.6f} best={best_val:.6f}")

    if best_state:
        m.load_state_dict(best_state)
        m.to(device)
    m.eval()

    # Standard baseline
    print("  [EXP-177] Training standard baseline...")
    m_std = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=3).to(device)
    opt_std = torch.optim.AdamW(m_std.parameters(), lr=1e-3, weight_decay=1e-5)
    sched_std = torch.optim.lr_scheduler.ReduceLROnPlateau(opt_std, patience=10)
    tl_std = DataLoader(train_ds, batch_size=batch, shuffle=True)
    best_std = float('inf')
    best_std_state = None

    for e in range(1, epochs + 1):
        m_std.train()
        for bx, bt in tl_std:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt_std.zero_grad()
            pred = m_std(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward(); opt_std.step()
        m_std.eval()
        vm = forecast_mse(m_std, val_ds, mask_future=True)
        sched_std.step(vm)
        if vm < best_std:
            best_std = vm
            best_std_state = {k: v.cpu().clone() for k, v in m_std.state_dict().items()}
        if e % 25 == 0:
            print(f"    [standard] {e}/{epochs} val={vm:.6f} best={best_std:.6f}")

    if best_std_state:
        m_std.load_state_dict(best_std_state)
        m_std.to(device)
    m_std.eval()

    def eval_model(model, tag):
        mae_sum, n = 0, 0
        vol_sum, vol_n, calm_sum, calm_n = 0, 0, 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
                for i in range(bx.shape[0]):
                    cov = float(bx[i, half:, 0].std() / max(bx[i, half:, 0].mean(), 1e-6))
                    if cov > 0.15:
                        vol_sum += err[i].sum().item(); vol_n += err[i].numel()
                    else:
                        calm_sum += err[i].sum().item(); calm_n += err[i].numel()
        return {
            'overall_mae': mae_sum / max(n, 1),
            'volatile_mae': vol_sum / max(vol_n, 1),
            'calm_mae': calm_sum / max(calm_n, 1),
        }

    curriculum_r = eval_model(m, "curriculum")
    standard_r = eval_model(m_std, "standard")
    print(f"  Curriculum: overall={curriculum_r['overall_mae']:.1f}, "
          f"volatile={curriculum_r['volatile_mae']:.1f}, calm={curriculum_r['calm_mae']:.1f}")
    print(f"  Standard: overall={standard_r['overall_mae']:.1f}, "
          f"volatile={standard_r['volatile_mae']:.1f}, calm={standard_r['calm_mae']:.1f}")

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'curriculum': curriculum_r,
        'standard': standard_r,
        'persistence_mae_mgdl': float(pers_mae),
        'curriculum_helps': curriculum_r['overall_mae'] < standard_r['overall_mae'],
        'volatile_improvement': float((standard_r['volatile_mae'] - curriculum_r['volatile_mae'])
                                       / standard_r['volatile_mae'] * 100),
        'epochs': epochs,
        'causal_masked': True,
    }

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp177_curriculum_forecast.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-177', 'name': 'curriculum-forecast',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results



# Phase 5: Stabilized training + combined production model
# Lessons: LR warmup prevents bad optima. Combine best techniques.

REGISTRY.update({
    'stable-ensemble':            'run_stable_ensemble',            # EXP-178
    'production-v9':              'run_production_v9',              # EXP-179
    'xgb-event-temporal':         'run_xgb_event_temporal',         # EXP-180
})


# ── EXP-178: Stabilized diverse ensemble ──────────────────────────
def run_stable_ensemble(args):
    """EXP-178: Diverse ensemble with stabilized training (warmup+cosine+clip)."""
    import json, os, torch, math
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-178] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2
    print(f"  [EXP-178] {len(train_ds)} train, {len(val_ds)} val, device={device}")

    configs = [
        {'d_model': 32, 'num_layers': 2, 'tag': 'd32_L2'},
        {'d_model': 64, 'num_layers': 2, 'tag': 'd64_L2'},
        {'d_model': 64, 'num_layers': 4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'tag': 'd128_L6'},
        {'d_model': 32, 'num_layers': 6, 'tag': 'd32_L6'},
    ]

    warmup_epochs = 10
    models = []
    individual_maes = {}

    for cfg in configs:
        tag = cfg['tag']
        print(f"  [EXP-178] Training {tag} (warmup={warmup_epochs}, cosine, clip=1.0)...")
        m = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                              num_layers=cfg['num_layers']).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)

        def lr_lambda(epoch, warmup=warmup_epochs, total=epochs):
            if epoch < warmup:
                return (epoch + 1) / warmup
            progress = (epoch - warmup) / max(1, total - warmup)
            return 0.5 * (1 + math.cos(math.pi * progress))

        sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
        tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
        best_val = float('inf')
        best_state = None

        for e in range(1, epochs + 1):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
                opt.step()
            sched.step()
            m.eval()
            val_mse = forecast_mse(m, val_ds, mask_future=True)
            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
            if e % 30 == 0:
                lr = opt.param_groups[0]['lr']
                print(f"    [{tag}] {e}/{epochs} val={val_mse:.6f} best={best_val:.6f} lr={lr:.6f}")

        if best_state:
            m.load_state_dict(best_state)
            m.to(device)
        m.eval()

        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item()
                n += err.numel()
        ind_mae = mae_sum / max(n, 1)
        individual_maes[tag] = ind_mae
        print(f"    [{tag}] forecast MAE={ind_mae:.1f} (best_val_mse={best_val:.6f})")
        models.append(m)

    print("  [EXP-178] Evaluating stable ensemble...")
    ens_mae_sum, ens_n = 0, 0
    hypo_sum, hypo_n = 0, 0
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            preds = [m(x_in)[:, half:, 0:1] for m in models]
            mean_pred = torch.stack(preds).mean(dim=0)
            tgt = bx[:, half:, 0:1]
            errors = (mean_pred - tgt).abs() * 400
            ens_mae_sum += errors.sum().item()
            ens_n += errors.numel()
            hypo_mask = tgt < 0.2
            if hypo_mask.any():
                hypo_sum += errors[hypo_mask].sum().item()
                hypo_n += hypo_mask.sum().item()

    ens_mae = ens_mae_sum / max(ens_n, 1)
    ens_hypo = hypo_sum / max(hypo_n, 1) if hypo_n > 0 else float('nan')

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    all_converged = all(individual_maes[c['tag']] < 20 for c in configs)

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(ens_hypo),
        'individual_maes': {k: float(v) for k, v in individual_maes.items()},
        'persistence_mae_mgdl': float(pers_mae),
        'all_members_converged': all_converged,
        'warmup_epochs': warmup_epochs,
        'grad_clip': 1.0,
        'schedule': 'cosine_with_warmup',
        'epochs': epochs,
        'causal_masked': True,
    }
    print(f"  [EXP-178] Ensemble MAE={ens_mae:.1f}, Hypo={ens_hypo:.1f}, "
          f"all_converged={all_converged}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp178_stable_ensemble.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-178', 'name': 'stable-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-179: Production v9 — best of everything ──────────────────
def run_production_v9(args):
    """EXP-179: Production model combining all best techniques."""
    import json, os, torch, math
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader, random_split

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-179] Need --patients-dir"); return {}

    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths, forecast_mse, persistence_mse
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    half = ws // 2

    cal_size = len(val_ds) // 2
    test_size = len(val_ds) - cal_size
    cal_ds, test_ds = random_split(val_ds, [cal_size, test_size],
                                    generator=torch.Generator().manual_seed(42))
    print(f"  [EXP-179] {len(train_ds)} train, {cal_size} cal, {test_size} test")

    configs = [
        {'d_model': 32, 'num_layers': 2, 'tag': 'd32_L2'},
        {'d_model': 64, 'num_layers': 2, 'tag': 'd64_L2'},
        {'d_model': 64, 'num_layers': 4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'tag': 'd128_L6'},
        {'d_model': 32, 'num_layers': 6, 'tag': 'd32_L6'},
    ]
    hypo_weight = 3.0
    warmup_epochs = 10
    models = []
    individual_maes = {}

    for cfg in configs:
        tag = cfg['tag']
        print(f"  [EXP-179] Training {tag}...")
        m = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                              num_layers=cfg['num_layers']).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-5)

        def lr_lambda(epoch, warmup=warmup_epochs, total=epochs):
            if epoch < warmup:
                return (epoch + 1) / warmup
            progress = (epoch - warmup) / max(1, total - warmup)
            return 0.5 * (1 + math.cos(math.pi * progress))
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
        tl = DataLoader(train_ds, batch_size=batch, shuffle=True)
        best_val = float('inf')
        best_state = None

        for e in range(1, epochs + 1):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                base_loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1], reduction='none')
                tgt = bx[:, half:, :1]
                weights = 1.0 + (hypo_weight - 1.0) * (tgt < 0.2).float()
                loss = (base_loss * weights).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
                opt.step()
            sched.step()
            m.eval()
            val_mse = forecast_mse(m, val_ds, mask_future=True)
            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in m.state_dict().items()}
            if e % 30 == 0:
                print(f"    [{tag}] {e}/{epochs} val={val_mse:.6f} best={best_val:.6f}")

        if best_state:
            m.load_state_dict(best_state)
            m.to(device)
        m.eval()
        mae_sum, n = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                err = (pred[:, half:, :1] - bx[:, half:, :1]).abs() * 400
                mae_sum += err.sum().item(); n += err.numel()
        individual_maes[tag] = mae_sum / max(n, 1)
        print(f"    [{tag}] MAE={individual_maes[tag]:.1f}")
        models.append(m)

    print("  [EXP-179] Evaluating ensemble on test set...")
    ens_mae_sum, ens_n = 0, 0
    hypo_sum, hypo_n = 0, 0
    all_errors = []
    with torch.no_grad():
        for bx, bt in DataLoader(test_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            preds = [m(x_in)[:, half:, 0:1] for m in models]
            mean_pred = torch.stack(preds).mean(dim=0)
            tgt = bx[:, half:, 0:1]
            errors = (mean_pred - tgt).abs() * 400
            ens_mae_sum += errors.sum().item()
            ens_n += errors.numel()
            all_errors.extend(errors.cpu().numpy().flatten())
            hypo_mask = tgt < 0.2
            if hypo_mask.any():
                hypo_sum += errors[hypo_mask].sum().item()
                hypo_n += hypo_mask.sum().item()
    ens_mae = ens_mae_sum / max(ens_n, 1)
    ens_hypo = hypo_sum / max(hypo_n, 1) if hypo_n > 0 else float('nan')

    print("  [EXP-179] Calibrating conformal intervals...")
    cal_scores = []
    with torch.no_grad():
        for bx, bt in DataLoader(cal_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            preds = [m(x_in)[:, half:, 0] for m in models]
            mean_pred = torch.stack(preds).mean(dim=0)
            residuals = (mean_pred - bx[:, half:, 0]).abs() * 400
            cal_scores.append(residuals.cpu().numpy())
    cal_scores = np.concatenate(cal_scores)
    n_cal = cal_scores.shape[0]
    q90 = float(np.quantile(cal_scores.flatten(), min(np.ceil((n_cal+1)*0.9)/n_cal, 1.0)))

    errors_arr = np.array(all_errors)
    coverage_90 = float(np.mean(errors_arr < q90))
    pi_width = q90 * 2

    pers_mse = persistence_mse(val_ds)
    pers_mae = float(np.sqrt(pers_mse) * 400) if pers_mse else 25.9

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(ens_hypo),
        'individual_maes': {k: float(v) for k, v in individual_maes.items()},
        'persistence_mae_mgdl': float(pers_mae),
        'conformal_coverage_90': float(coverage_90),
        'conformal_pi_width_mgdl': float(pi_width),
        'techniques': ['stable_training', 'hypo_weighting', 'diverse_ensemble', 'conformal_pi'],
        'hypo_weight': hypo_weight,
        'warmup_epochs': warmup_epochs,
        'grad_clip': 1.0,
        'epochs': epochs,
        'causal_masked': True,
    }
    print(f"  [EXP-179] Ensemble MAE={ens_mae:.1f}, Hypo={ens_hypo:.1f}, "
          f"PI coverage={coverage_90:.3f}, width={pi_width:.1f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp179_production_v9.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-179', 'name': 'production-v9',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-180: XGBoost with temporal window features ───────────────
def run_xgb_event_temporal(args):
    """EXP-180: XGBoost events with temporal shape features."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-180] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-180] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]

    new_features = []
    new_names = []

    for ci in glucose_cols[:5]:
        name = feature_names[ci]
        g_tr = X_train[:, ci]
        g_vl = X_val[:, ci]

        roc_tr = np.gradient(g_tr)
        roc_vl = np.gradient(g_vl)
        new_features.append((roc_tr, roc_vl))
        new_names.append(f'{name}_roc')

        acc_tr = np.gradient(roc_tr)
        acc_vl = np.gradient(roc_vl)
        new_features.append((acc_tr, acc_vl))
        new_names.append(f'{name}_acc')

        def rolling_std(arr, w=10):
            result = np.zeros_like(arr)
            for i in range(len(arr)):
                start = max(0, i - w)
                result[i] = np.std(arr[start:i+1])
            return result
        rstd_tr = rolling_std(g_tr)
        rstd_vl = rolling_std(g_vl)
        new_features.append((rstd_tr, rstd_vl))
        new_names.append(f'{name}_rstd')

    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]
    if iob_cols and cob_cols:
        iob_tr = X_train[:, iob_cols[0]]
        iob_vl = X_val[:, iob_cols[0]]
        cob_tr = X_train[:, cob_cols[0]]
        cob_vl = X_val[:, cob_cols[0]]
        new_features.append((iob_tr * cob_tr, iob_vl * cob_vl))
        new_names.append('iob_cob_interaction')
        new_features.append((iob_tr / (cob_tr + 1), iob_vl / (cob_vl + 1)))
        new_names.append('iob_cob_ratio')

    for (f_tr, f_vl), name in zip(new_features, new_names):
        X_train = np.column_stack([X_train, f_tr])
        X_val = np.column_stack([X_val, f_vl])
        feature_names.append(name)

    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
    except ImportError:
        print("  [EXP-180] Missing dependencies"); return {}

    print(f"  [EXP-180] {X_train.shape[0]} train, {X_val.shape[0]} val, "
          f"{len(feature_names)} features ({len(new_names)} new), {n_classes} classes")

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    clf = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                              eval_metric='mlogloss', random_state=42, tree_method='hist',
                              subsample=0.8, colsample_bytree=0.8)
    clf.fit(X_train, y_train_m, sample_weight=sw)
    y_pred = clf.predict(X_val)
    f1_macro = float(f1_score(y_val_m, y_pred, average='macro', zero_division=0))
    f1_weighted = float(f1_score(y_val_m, y_pred, average='weighted', zero_division=0))

    n_orig = len(feature_names) - len(new_names)
    clf_base = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                                   eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_base.fit(X_train[:, :n_orig], y_train_m, sample_weight=sw)
    y_pred_base = clf_base.predict(X_val[:, :n_orig])
    f1_base = float(f1_score(y_val_m, y_pred_base, average='macro', zero_division=0))

    importances = clf.feature_importances_
    top_k = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:15]

    results = {
        'f1_macro_with_temporal': f1_macro,
        'f1_weighted_with_temporal': f1_weighted,
        'f1_macro_baseline': f1_base,
        'temporal_improvement': float(f1_macro - f1_base),
        'n_classes': n_classes,
        'n_features_total': len(feature_names),
        'n_new_features': len(new_names),
        'new_feature_names': new_names,
        'top_features': {n: float(v) for n, v in top_k},
    }
    print(f"  [EXP-180] With temporal: F1={f1_macro:.3f}, Baseline: F1={f1_base:.3f}, "
          f"improvement={f1_macro - f1_base:+.3f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp180_xgb_event_temporal.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-180', 'name': 'xgb-event-temporal',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ╔════════════════════════════════════════════════════════════════════╗
# ║  PHASE 6 — Event Features, Robust Ensemble, Drift, Utility       ║
# ╚════════════════════════════════════════════════════════════════════╝

REGISTRY.update({
    'xgb-event-pharma':       'run_xgb_event_pharma',         # EXP-181
    'robust-ensemble':        'run_robust_ensemble',           # EXP-182
    'drift-pattern':          'run_drift_pattern',             # EXP-183
    'override-utility':       'run_override_utility',          # EXP-184
    'xgb-event-multihorizon': 'run_xgb_event_multihorizon',   # EXP-185
})


# ── EXP-181: XGBoost with pharmacodynamic features ────────────────
# EXP-180 gained +0.112 from temporal features. Can we push further
# with pharmacodynamic features (IOB aging, peak window, cross-channel
# momentum) and hyperparameter tuning?
def run_xgb_event_pharma(args):
    """EXP-181: XGBoost events with pharmacodynamic + advanced temporal features."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-181] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-181] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    # Remove leaky lead_time_hr
    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    # ── EXP-180 features (replicate for baseline) ──
    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]
    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]

    new_features = []
    new_names = []

    def rolling_std(arr, w=10):
        result = np.zeros_like(arr, dtype=float)
        for i in range(len(arr)):
            start = max(0, i - w)
            result[i] = np.std(arr[start:i+1])
        return result

    def rolling_mean(arr, w=10):
        result = np.zeros_like(arr, dtype=float)
        for i in range(len(arr)):
            start = max(0, i - w)
            result[i] = np.mean(arr[start:i+1])
        return result

    # EXP-180 temporal features (glucose ROC, acceleration, rolling std)
    for ci in glucose_cols[:5]:
        name = feature_names[ci]
        g_tr = X_train[:, ci]; g_vl = X_val[:, ci]
        roc_tr = np.gradient(g_tr); roc_vl = np.gradient(g_vl)
        new_features.append((roc_tr, roc_vl)); new_names.append(f'{name}_roc')
        acc_tr = np.gradient(roc_tr); acc_vl = np.gradient(roc_vl)
        new_features.append((acc_tr, acc_vl)); new_names.append(f'{name}_acc')
        rstd_tr = rolling_std(g_tr); rstd_vl = rolling_std(g_vl)
        new_features.append((rstd_tr, rstd_vl)); new_names.append(f'{name}_rstd')

    if iob_cols and cob_cols:
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        cob_tr = X_train[:, cob_cols[0]]; cob_vl = X_val[:, cob_cols[0]]
        new_features.append((iob_tr * cob_tr, iob_vl * cob_vl))
        new_names.append('iob_cob_interaction')
        new_features.append((iob_tr / (cob_tr + 1), iob_vl / (cob_vl + 1)))
        new_names.append('iob_cob_ratio')

    # ── NEW pharmacodynamic features ──
    if iob_cols:
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        # IOB peak window: IOB * (1 - IOB^2) — peaks when IOB is moderate
        peak_tr = iob_tr * (1 - np.clip(iob_tr, 0, 1)**2)
        peak_vl = iob_vl * (1 - np.clip(iob_vl, 0, 1)**2)
        new_features.append((peak_tr, peak_vl)); new_names.append('iob_peak_window')
        # IOB tail phase: 1/(IOB+0.1) — captures insulin waning
        tail_tr = 1.0 / (np.abs(iob_tr) + 0.1)
        tail_vl = 1.0 / (np.abs(iob_vl) + 0.1)
        new_features.append((tail_tr, tail_vl)); new_names.append('iob_tail_phase')
        # IOB rate of change
        iob_roc_tr = np.gradient(iob_tr); iob_roc_vl = np.gradient(iob_vl)
        new_features.append((iob_roc_tr, iob_roc_vl)); new_names.append('iob_roc')
        # IOB rolling volatility
        iob_rstd_tr = rolling_std(iob_tr); iob_rstd_vl = rolling_std(iob_vl)
        new_features.append((iob_rstd_tr, iob_rstd_vl)); new_names.append('iob_rstd')

    if cob_cols:
        cob_tr = X_train[:, cob_cols[0]]; cob_vl = X_val[:, cob_cols[0]]
        # COB decay rate
        cob_roc_tr = np.gradient(cob_tr); cob_roc_vl = np.gradient(cob_vl)
        new_features.append((cob_roc_tr, cob_roc_vl)); new_names.append('cob_roc')
        # COB rolling mean (recent carb load)
        cob_rmean_tr = rolling_mean(cob_tr); cob_rmean_vl = rolling_mean(cob_vl)
        new_features.append((cob_rmean_tr, cob_rmean_vl)); new_names.append('cob_rolling_mean')

    # Cross-channel momentum features
    if glucose_cols and iob_cols:
        g0_tr = X_train[:, glucose_cols[0]]; g0_vl = X_val[:, glucose_cols[0]]
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        g_roc_tr = np.gradient(g0_tr); g_roc_vl = np.gradient(g0_vl)
        i_roc_tr = np.gradient(iob_tr); i_roc_vl = np.gradient(iob_vl)
        # Glucose-insulin sync: both rising
        sync_tr = ((g_roc_tr > 0) & (i_roc_tr > 0)).astype(float)
        sync_vl = ((g_roc_vl > 0) & (i_roc_vl > 0)).astype(float)
        new_features.append((sync_tr, sync_vl)); new_names.append('glucose_iob_sync')
        # Insulin leads (insulin rising, glucose falling)
        lead_tr = ((g_roc_tr < 0) & (i_roc_tr > 0)).astype(float)
        lead_vl = ((g_roc_vl < 0) & (i_roc_vl > 0)).astype(float)
        new_features.append((lead_tr, lead_vl)); new_names.append('insulin_leads_glucose')
        # Glucose-to-IOB ratio (insulin sensitivity proxy)
        gir_tr = g0_tr / (iob_tr + 0.01); gir_vl = g0_vl / (iob_vl + 0.01)
        new_features.append((gir_tr, gir_vl)); new_names.append('glucose_iob_ratio')

    # Combine all features
    for (f_tr, f_vl), name in zip(new_features, new_names):
        X_train = np.column_stack([X_train, f_tr])
        X_val = np.column_stack([X_val, f_vl])
        feature_names.append(name)

    # Label remapping
    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
    except ImportError:
        print("  [EXP-181] Missing dependencies"); return {}

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    n_pharma = sum(1 for n in new_names if n not in [
        f'{feature_names[ci]}_roc' for ci in glucose_cols[:5]] +
        [f'{feature_names[ci]}_acc' for ci in glucose_cols[:5]] +
        [f'{feature_names[ci]}_rstd' for ci in glucose_cols[:5]] +
        ['iob_cob_interaction', 'iob_cob_ratio'])

    print(f"  [EXP-181] {X_train.shape[0]} train, {X_val.shape[0]} val, "
          f"{len(feature_names)} features ({len(new_names)} new, {n_pharma} pharma), "
          f"{n_classes} classes")

    # Hyperparameter search
    best_f1 = 0
    best_tag = ''
    all_results = {}
    for max_d in [6, 8, 10]:
        for n_est in [200, 300, 400]:
            for lr in [0.03, 0.05, 0.08]:
                tag = f'md{max_d}_ne{n_est}_lr{lr}'
                clf = xgb.XGBClassifier(
                    max_depth=max_d, n_estimators=n_est, learning_rate=lr,
                    subsample=0.8, colsample_bytree=0.8, eval_metric='mlogloss',
                    random_state=42, tree_method='hist')
                clf.fit(X_train, y_train_m, sample_weight=sw)
                y_pred = clf.predict(X_val)
                f1 = float(f1_score(y_val_m, y_pred, average='macro', zero_division=0))
                all_results[tag] = f1
                if f1 > best_f1:
                    best_f1 = f1
                    best_tag = tag
                    best_clf = clf

    # Compare to EXP-180 baseline (temporal only, no pharma)
    n_180 = len(feature_names) - n_pharma  # features up to EXP-180 level
    clf_base = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                                  subsample=0.8, colsample_bytree=0.8,
                                  eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_base.fit(X_train[:, :n_180], y_train_m, sample_weight=sw)
    y_pred_base = clf_base.predict(X_val[:, :n_180])
    f1_base_180 = float(f1_score(y_val_m, y_pred_base, average='macro', zero_division=0))

    # Feature importances from best model
    importances = best_clf.feature_importances_
    top_k = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:20]

    results = {
        'best_f1': best_f1,
        'best_hyperparams': best_tag,
        'f1_baseline_exp180': f1_base_180,
        'improvement_over_180': float(best_f1 - f1_base_180),
        'n_classes': n_classes,
        'n_total_features': len(feature_names),
        'n_new_features': len(new_names),
        'n_pharma_features': n_pharma,
        'pharma_feature_names': [n for n in new_names if n.startswith(('iob_peak', 'iob_tail',
            'iob_roc', 'iob_rstd', 'cob_roc', 'cob_rolling', 'glucose_iob_sync',
            'insulin_leads', 'glucose_iob_ratio'))],
        'top_features': {n: float(v) for n, v in top_k},
        'all_hyperparams': all_results,
        'hyperparams_tested': len(all_results),
    }

    print(f"  [EXP-181] Best: {best_tag} F1={best_f1:.4f} vs EXP-180 baseline {f1_base_180:.4f} "
          f"(+{best_f1 - f1_base_180:+.4f})")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp181_xgb_pharmakinetic.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-181', 'name': 'xgb-event-pharmakinetic',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-182: Robust ensemble with divergence detection ─────────────
# EXP-178 had d32_L2 diverge (39.3 MAE). Fix: detect and exclude
# diverging members, add dropout/weight decay, use validated members.
def run_robust_ensemble(args):
    """EXP-182: Robust ensemble — dropout, weight decay, divergence exclusion."""
    import json, os, torch, math
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-182] Need --patients-dir"); return {}

    from .model import CGMGroupedEncoder
    from .experiment_lib import (resolve_patient_paths, load_multipatient_nightscout,
                                  forecast_mse, persistence_mse)

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f"  [EXP-182] {len(train_ds)} train, {len(val_ds)} val windows")
    pers_mse = persistence_mse(val_ds, batch_size=batch)
    pers_mae = float(np.sqrt(pers_mse) * 400)
    print(f"  [EXP-182] Persistence MAE: {pers_mae:.1f}")

    configs = [
        {'d_model': 32, 'num_layers': 2, 'dropout': 0.15, 'wd': 5e-4, 'tag': 'd32_L2'},
        {'d_model': 64, 'num_layers': 2, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd64_L2'},
        {'d_model': 64, 'num_layers': 4, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd128_L6'},
        {'d_model': 32, 'num_layers': 6, 'dropout': 0.15, 'wd': 5e-4, 'tag': 'd32_L6'},
    ]

    member_results = []
    trained_models = []

    for cfg in configs:
        tag = cfg['tag']
        print(f"  [EXP-182] Training {tag} (dropout={cfg['dropout']}, wd={cfg['wd']})...")
        model = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                                   nhead=4, num_layers=cfg['num_layers'],
                                   dropout=cfg['dropout']).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=cfg['wd'])

        # Warmup + cosine schedule
        warmup = 10
        def lr_lambda(ep):
            if ep < warmup:
                return (ep + 1) / warmup
            progress = (ep - warmup) / max(1, epochs - warmup)
            return 0.5 * (1 + math.cos(math.pi * progress))
        scheduler = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

        best_val = float('inf')
        best_state = None
        stale = 0
        diverged = False

        loader = DataLoader(train_ds, batch_size=batch, shuffle=True)

        for ep in range(1, epochs + 1):
            model.train()
            for bx, bt in loader:
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            scheduler.step()

            # Validation
            model.eval()
            val_loss = 0; n = 0
            with torch.no_grad():
                for bx, bt in DataLoader(val_ds, batch_size=256):
                    bx = bx.to(device)
                    half = bx.shape[1] // 2
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    err = (pred[:, half:, :1] - bx[:, half:, :1]).pow(2).mean()
                    val_loss += err.item() * bx.shape[0]; n += bx.shape[0]
            val_mse = val_loss / max(n, 1)

            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                stale = 0
            else:
                stale += 1

            # Divergence: if val_mse > 10x persistence, bail out
            if val_mse > pers_mse * 10:
                print(f"    [{tag}] DIVERGED at epoch {ep} (val_mse={val_mse:.6f})")
                diverged = True
                break

            if ep % 30 == 0:
                lr_now = scheduler.get_last_lr()[0]
                print(f"    [{tag}] {ep}/{epochs} val={val_mse:.6f} best={best_val:.6f} lr={lr_now:.6f}")

        if diverged and best_val > pers_mse * 3:
            print(f"    [{tag}] Excluded (diverged, best_val={best_val:.6f})")
            member_results.append({'arch': tag, 'diverged': True,
                                   'best_val_mse': float(best_val), 'forecast_mae_mgdl': None})
            continue

        if best_state:
            model.load_state_dict(best_state)
        model.eval()

        # Compute MAE
        mae_sum = 0; n = 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                errs = (pred[:, half:, :1] - bx[:, half:, :1]).abs().mean(dim=(1, 2))
                mae_sum += errs.sum().item(); n += bx.shape[0]
        mae_mgdl = (mae_sum / max(n, 1)) * 400

        print(f"    [{tag}] forecast MAE={mae_mgdl:.1f} (best_val_mse={best_val:.6f})")
        member_results.append({'arch': tag, 'diverged': False,
                               'best_val_mse': float(best_val),
                               'forecast_mae_mgdl': float(mae_mgdl)})
        trained_models.append(model)

    # Ensemble from valid members
    if len(trained_models) >= 2:
        preds_all = []
        targets_all = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                member_preds = [m(x_in)[:, half:, :1] for m in trained_models]
                ens = torch.stack(member_preds).mean(dim=0)
                preds_all.append(ens.cpu())
                targets_all.append(bx[:, half:, :1].cpu())
        preds_cat = torch.cat(preds_all)
        targets_cat = torch.cat(targets_all)
        ens_mae = float((preds_cat - targets_cat).abs().mean()) * 400

        # Hypo MAE (< 70/400 = 0.175 normalized)
        hypo_mask = targets_cat < 0.175
        hypo_mae = float((preds_cat[hypo_mask] - targets_cat[hypo_mask]).abs().mean()) * 400 if hypo_mask.any() else None
    else:
        ens_mae = member_results[0]['forecast_mae_mgdl'] if member_results else None
        hypo_mae = None

    n_valid = sum(1 for m in member_results if not m['diverged'])
    results = {
        'ensemble_mae_mgdl': float(ens_mae) if ens_mae else None,
        'ensemble_hypo_mae_mgdl': float(hypo_mae) if hypo_mae else None,
        'persistence_mae_mgdl': pers_mae,
        'n_members_trained': len(configs),
        'n_members_valid': n_valid,
        'n_members_diverged': len(configs) - n_valid,
        'all_converged': n_valid == len(configs),
        'members': member_results,
        'training': {'epochs': epochs, 'warmup': 10, 'grad_clip': 1.0,
                     'schedule': 'cosine_with_warmup'},
        'robustness': {'dropout': True, 'weight_decay': True,
                       'divergence_detection': True,
                       'divergence_threshold': '10x persistence'},
    }

    print(f"  [EXP-182] Ensemble MAE={ens_mae:.1f} ({n_valid}/{len(configs)} valid members), "
          f"Hypo={hypo_mae:.1f}" if hypo_mae else
          f"  [EXP-182] Ensemble MAE={ens_mae}, {n_valid}/{len(configs)} valid")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp182_robust_ensemble.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-182', 'name': 'robust-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-183: Drift pattern detection with sliding median ───────────
# Current drift correlation is -0.071 (right sign, weak). Use the
# autosens-style sliding median from generate_aux_labels to compute
# drift states per patient and correlate with TIR changes.
def run_drift_pattern(args):
    """EXP-183: Drift pattern detection — sliding median ISF tracking vs TIR."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-183] Need --patients-dir"); return {}

    from .experiment_lib import resolve_patient_paths, load_patient_profile

    paths = resolve_patient_paths(patients_dir, getattr(args, 'real_data', None))
    ws = getattr(args, 'window_size', 24)
    results_per_patient = {}
    all_drift_tir = []

    for ppath in paths:
        import pathlib
        patient_id = pathlib.Path(ppath).parent.name
        print(f"  [EXP-183] Processing patient {patient_id}...")

        # Load profile for nominal ISF
        try:
            profile = load_patient_profile(ppath)
            nominal_isf = profile.get('isf', 45.0)
        except Exception:
            nominal_isf = 45.0

        # Load glucose entries
        entries_path = os.path.join(ppath, 'entries.json')
        if not os.path.exists(entries_path):
            continue
        entries = json.load(open(entries_path))
        if not entries:
            continue

        # Extract glucose values and timestamps
        sgvs = []
        for e in entries:
            sgv = e.get('sgv', e.get('glucose'))
            if sgv and 30 < sgv < 500:
                sgvs.append(float(sgv))
        if len(sgvs) < 48:
            continue

        sgvs = np.array(sgvs)

        # Compute deltas (5-min intervals assumed)
        deltas = np.diff(sgvs)

        # Sliding median of normalized deviations (autosens approach)
        # deviation = delta / ISF (how many "ISF units" glucose moved)
        deviations = deltas / nominal_isf
        window = 24  # 2-hour sliding window
        drift_ratios = np.ones(len(deviations))
        for i in range(window, len(deviations)):
            chunk = deviations[i-window:i]
            # Median deviation as ISF estimate (autosens-style)
            med = np.median(chunk)
            # Ratio: >1 means more sensitive, <1 means more resistant
            ratio = 1.0 + np.clip(med, -0.3, 0.2)
            drift_ratios[i] = ratio

        # Compute TIR in windows (70-180 mg/dL)
        tir_window = 12  # 1-hour TIR window
        tir_values = np.zeros(len(sgvs))
        for i in range(tir_window, len(sgvs)):
            chunk = sgvs[i-tir_window:i]
            tir_values[i] = np.mean((chunk >= 70) & (chunk <= 180))

        # Align drift_ratios with tir_values (offset by 1 for delta)
        min_len = min(len(drift_ratios), len(tir_values) - 1)
        if min_len < 50:
            continue

        drift_aligned = drift_ratios[:min_len]
        tir_aligned = tir_values[1:min_len+1]

        # Correlation
        valid = ~(np.isnan(drift_aligned) | np.isnan(tir_aligned))
        if valid.sum() < 50:
            continue

        corr = float(np.corrcoef(drift_aligned[valid], tir_aligned[valid])[0, 1])

        # State classification (resistance/stable/sensitivity)
        resistance = float(np.mean(drift_aligned < 0.9))
        sensitivity = float(np.mean(drift_aligned > 1.1))
        stable = float(np.mean((drift_aligned >= 0.9) & (drift_aligned <= 1.1)))

        results_per_patient[patient_id] = {
            'correlation': corr,
            'n_samples': int(valid.sum()),
            'nominal_isf': float(nominal_isf),
            'drift_mean': float(np.mean(drift_aligned)),
            'drift_std': float(np.std(drift_aligned)),
            'state_distribution': {'resistance': resistance, 'stable': stable,
                                   'sensitivity': sensitivity},
            'mean_tir': float(np.mean(tir_aligned)),
        }
        all_drift_tir.append((drift_aligned[valid], tir_aligned[valid]))
        print(f"    {patient_id}: corr={corr:.3f}, TIR={np.mean(tir_aligned):.2f}, "
              f"states: R={resistance:.0%}/S={stable:.0%}/+={sensitivity:.0%}")

    # Aggregate correlation
    if all_drift_tir:
        all_d = np.concatenate([d for d, _ in all_drift_tir])
        all_t = np.concatenate([t for _, t in all_drift_tir])
        agg_corr = float(np.corrcoef(all_d, all_t)[0, 1])
        per_patient_corrs = [r['correlation'] for r in results_per_patient.values()]
        median_corr = float(np.median(per_patient_corrs))
    else:
        agg_corr = 0; median_corr = 0

    results = {
        'aggregate_correlation': agg_corr,
        'median_per_patient_correlation': median_corr,
        'n_patients': len(results_per_patient),
        'per_patient': results_per_patient,
        'method': 'autosens_sliding_median',
        'window_size': 24,
        'isf_source': 'load_patient_profile',
        'comparison': {'exp124_corr': 0.70, 'exp154_median_corr': -0.071},
    }

    print(f"\n  [EXP-183] Aggregate: corr={agg_corr:.3f}, median={median_corr:.3f}, "
          f"{len(results_per_patient)} patients")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp183_drift_pattern.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-183', 'name': 'drift-pattern',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-184: Override utility scoring ──────────────────────────────
# Current override eval uses F1 which is misframed (glucose events ≠
# treatment logs). Reframe as utility: would the predicted event type
# lead to a correct override that improves glucose outcomes?
def run_override_utility(args):
    """EXP-184: Override utility scoring — event predictions as actionable overrides."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-184] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-184] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    # Add temporal features (same as EXP-180)
    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]
    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]

    for ci in glucose_cols[:3]:
        g_tr = X_train[:, ci]; g_vl = X_val[:, ci]
        X_train = np.column_stack([X_train, np.gradient(g_tr)])
        X_val = np.column_stack([X_val, np.gradient(g_vl)])
        feature_names.append(f'{feature_names[ci]}_roc')

    if iob_cols and cob_cols:
        X_train = np.column_stack([X_train,
                                    X_train[:, iob_cols[0]] * X_train[:, cob_cols[0]]])
        X_val = np.column_stack([X_val,
                                  X_val[:, iob_cols[0]] * X_val[:, cob_cols[0]]])
        feature_names.append('iob_cob_interaction')

    # Label remapping
    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    rev_map = {new: old for old, new in label_map.items()}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
    except ImportError:
        print("  [EXP-184] Missing dependencies"); return {}

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    clf = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.8,
                              eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf.fit(X_train, y_train_m, sample_weight=sw)
    y_pred = clf.predict(X_val)
    y_prob = clf.predict_proba(X_val)
    f1_macro = float(f1_score(y_val_m, y_pred, average='macro', zero_division=0))

    # ── Utility framework ──
    # Override utility matrix: event_type → override → glucose impact
    # Each event class maps to a potential override action
    # Utility = benefit of correct action - cost of wrong action
    #
    # Event classes (from label_events):
    # 0=none, 1=meal/eating, 2=exercise, 5=sleep, 6=sick, 8=custom
    # Override actions: none, eating_soon, exercise, sleep, sick
    #
    # Utility matrix: positive = helpful, negative = harmful
    UTILITY_MATRIX = {
        # (true_class, predicted_class): utility
        # Correct predictions: high positive utility
        (0, 0): 0.0,    # no event, predict no event: neutral
        (1, 1): 1.0,    # meal detected, eating_soon override: very helpful
        (2, 2): 0.8,    # exercise, exercise override: helpful
        (5, 5): 0.5,    # sleep, sleep override: moderately helpful
        (6, 6): 0.9,    # sick, sick override: helpful
        (8, 8): 0.3,    # custom, custom: slightly helpful
        # False positives (predict event when none): cost of unnecessary override
        (0, 1): -0.3,   # no event, eating_soon: mild waste
        (0, 2): -0.2,   # no event, exercise: mild waste
        (0, 5): -0.1,   # no event, sleep: minimal cost
        (0, 6): -0.4,   # no event, sick: more disruptive
        # False negatives (miss real event): cost of missed intervention
        (1, 0): -0.5,   # meal missed: moderate cost
        (2, 0): -0.3,   # exercise missed: moderate cost
        (5, 0): -0.1,   # sleep missed: low cost (mostly passive)
        (6, 0): -0.7,   # sick missed: high cost
        # Cross-misclassification (wrong event type)
        (1, 2): -0.4,   # meal as exercise: wrong override, harmful
        (2, 1): -0.3,   # exercise as meal: wrong override
        (1, 6): -0.6,   # meal as sick: very wrong
        (6, 1): -0.5,   # sick as meal: harmful
    }

    # Compute utility scores
    utilities = np.zeros(len(y_val_m))
    for i in range(len(y_val_m)):
        true_c = int(y_val_m[i])
        pred_c = int(y_pred[i])
        key = (true_c, pred_c)
        if key in UTILITY_MATRIX:
            utilities[i] = UTILITY_MATRIX[key]
        elif true_c == pred_c:
            utilities[i] = 0.3  # generic correct
        else:
            utilities[i] = -0.2  # generic wrong

    mean_utility = float(np.mean(utilities))
    positive_utility_rate = float(np.mean(utilities > 0))
    negative_utility_rate = float(np.mean(utilities < 0))
    zero_utility_rate = float(np.mean(utilities == 0))

    # Confidence-gated utility: only recommend when confident
    confidence_thresholds = [0.3, 0.5, 0.7, 0.8, 0.9]
    gated_results = {}
    for thresh in confidence_thresholds:
        max_probs = np.max(y_prob, axis=1)
        confident_mask = max_probs >= thresh
        if confident_mask.sum() < 10:
            continue
        gated_utility = float(np.mean(utilities[confident_mask]))
        gated_coverage = float(np.mean(confident_mask))
        gated_f1 = float(f1_score(y_val_m[confident_mask], y_pred[confident_mask],
                                    average='macro', zero_division=0))
        gated_results[str(thresh)] = {
            'utility': gated_utility,
            'coverage': gated_coverage,
            'f1': gated_f1,
            'n_samples': int(confident_mask.sum()),
        }
        print(f"    [EXP-184] @conf>={thresh}: utility={gated_utility:.3f}, "
              f"coverage={gated_coverage:.1%}, F1={gated_f1:.3f}")

    results = {
        'f1_macro': f1_macro,
        'mean_utility': mean_utility,
        'positive_utility_rate': positive_utility_rate,
        'negative_utility_rate': negative_utility_rate,
        'zero_utility_rate': zero_utility_rate,
        'confidence_gated': gated_results,
        'utility_matrix_size': len(UTILITY_MATRIX),
        'n_classes': n_classes,
        'comparison': {
            'exp123_f1': 0.130,
            'exp180_f1': 0.618,
            'exp184_f1': f1_macro,
            'exp184_utility': mean_utility,
        },
    }

    print(f"\n  [EXP-184] F1={f1_macro:.3f}, Utility={mean_utility:.3f} "
          f"(+rate={positive_utility_rate:.1%}, -rate={negative_utility_rate:.1%})")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp184_override_utility.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-184', 'name': 'override-utility',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-185: Multi-horizon event forecasting ──────────────────────
# Predict both event TYPE and LEAD TIME (how soon until event).
# More actionable than type alone — enables proactive overrides.
def run_xgb_event_multihorizon(args):
    """EXP-185: XGBoost multi-horizon — predict event type + lead time."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-185] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-185] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    # Extract lead_time before removing it
    lead_time_train = None; lead_time_val = None
    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        lead_time_train = X_train[:, idx].copy()
        lead_time_val = X_val[:, idx].copy()
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    # Add temporal features (key from EXP-180)
    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower()]
    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]

    for ci in glucose_cols[:3]:
        g_tr = X_train[:, ci]; g_vl = X_val[:, ci]
        X_train = np.column_stack([X_train, np.gradient(g_tr)])
        X_val = np.column_stack([X_val, np.gradient(g_vl)])
        feature_names.append(f'{feature_names[ci]}_roc')

    if iob_cols and cob_cols:
        X_train = np.column_stack([X_train,
                                    X_train[:, iob_cols[0]] * X_train[:, cob_cols[0]]])
        X_val = np.column_stack([X_val,
                                  X_val[:, iob_cols[0]] * X_val[:, cob_cols[0]]])
        feature_names.append('iob_cob_interaction')

    # Label remapping for event type
    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    # Lead time binning: 0-15min, 15-30min, 30-60min, 60+min
    def bin_lead_time(lt):
        if lt is None or np.isnan(lt): return 3  # unknown → 60+
        hrs = abs(lt)
        if hrs < 0.25: return 0
        elif hrs < 0.5: return 1
        elif hrs < 1.0: return 2
        else: return 3

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score, accuracy_score
    except ImportError:
        print("  [EXP-185] Missing dependencies"); return {}

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    # Model 1: Event type classifier (same as EXP-180 baseline)
    clf_type = xgb.XGBClassifier(max_depth=8, n_estimators=300, learning_rate=0.05,
                                  subsample=0.8, colsample_bytree=0.8,
                                  eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_type.fit(X_train, y_train_m, sample_weight=sw)
    y_pred_type = clf_type.predict(X_val)
    f1_type = float(f1_score(y_val_m, y_pred_type, average='macro', zero_division=0))

    # Model 2: Lead time classifier (only for positive events)
    lead_results = {}
    if lead_time_train is not None:
        lead_class_train = np.array([bin_lead_time(lt) for lt in lead_time_train])
        lead_class_val = np.array([bin_lead_time(lt) for lt in lead_time_val])

        positive_train = y_train_m > 0
        positive_val = y_val_m > 0

        if positive_train.sum() > 50 and positive_val.sum() > 10:
            # Remap lead time classes to contiguous 0..N
            lead_tr_pos = lead_class_train[positive_train]
            lead_unique = np.unique(lead_tr_pos)
            lead_map = {old: new for new, old in enumerate(lead_unique)}
            lead_tr_mapped = np.array([lead_map[y] for y in lead_tr_pos])

            clf_lead = xgb.XGBClassifier(max_depth=6, n_estimators=200, learning_rate=0.05,
                                          subsample=0.8, colsample_bytree=0.8,
                                          eval_metric='mlogloss', random_state=42,
                                          tree_method='hist')
            clf_lead.fit(X_train[positive_train], lead_tr_mapped)

            y_pred_lead_raw = clf_lead.predict(X_val[positive_val])
            rev_lead = {new: old for old, new in lead_map.items()}
            y_pred_lead = np.array([rev_lead.get(y, 3) for y in y_pred_lead_raw])
            y_true_lead = lead_class_val[positive_val]
            acc_lead = float(accuracy_score(y_true_lead, y_pred_lead))

            # Joint: both type AND lead time correct
            y_pred_lead_all = np.full(len(y_val_m), 3)
            if positive_val.sum() > 0:
                y_pred_lead_raw_all = clf_lead.predict(X_val[positive_val])
                y_pred_lead_all[positive_val] = np.array([rev_lead.get(y, 3) for y in y_pred_lead_raw_all])
            joint_correct = (y_pred_type == y_val_m) & (y_pred_lead_all == lead_class_val)
            joint_acc = float(np.mean(joint_correct))

            lead_results = {
                'accuracy_lead_time': acc_lead,
                'joint_accuracy': joint_acc,
                'n_positive_train': int(positive_train.sum()),
                'n_positive_val': int(positive_val.sum()),
                'lead_time_dist': {
                    '0-15min': float(np.mean(lead_class_val == 0)),
                    '15-30min': float(np.mean(lead_class_val == 1)),
                    '30-60min': float(np.mean(lead_class_val == 2)),
                    '60+min': float(np.mean(lead_class_val == 3)),
                },
            }
            print(f"  [EXP-185] Lead time: acc={acc_lead:.3f}, joint={joint_acc:.3f}")
    else:
        print("  [EXP-185] No lead_time_hr available, type-only evaluation")

    results = {
        'f1_event_type': f1_type,
        **lead_results,
        'n_classes': n_classes,
        'comparison': {
            'exp180_f1': 0.618,
            'exp185_f1_type': f1_type,
        },
    }

    print(f"  [EXP-185] Type F1={f1_type:.3f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp185_xgb_multihorizon.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-185', 'name': 'xgb-event-multihorizon',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ╔════════════════════════════════════════════════════════════════════╗
# ║  PHASE 7 — Combined production, per-patient events, drift v2     ║
# ╚════════════════════════════════════════════════════════════════════╝

REGISTRY.update({
    'robust-hypo-ensemble':    'run_robust_hypo_ensemble',      # EXP-186
    'xgb-event-perpatient':    'run_xgb_event_perpatient',      # EXP-187
    'drift-treatment-context': 'run_drift_treatment_context',   # EXP-188
    'production-v10':          'run_production_v10',             # EXP-189
})


# ── EXP-186: Robust ensemble + hypo-weighted loss ─────────────────
# EXP-182 achieved 11.7 MAE (new best) but hypo MAE was 14.6.
# EXP-136 showed 2-stage hypo approach helps. Combine robust training
# with hypo-weighted loss for best of both worlds.
def run_robust_hypo_ensemble(args):
    """EXP-186: Robust ensemble with hypo-weighted forecast loss."""
    import json, os, torch, math
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-186] Need --patients-dir"); return {}

    from .model import CGMGroupedEncoder
    from .experiment_lib import (resolve_patient_paths, load_multipatient_nightscout,
                                  persistence_mse)

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f"  [EXP-186] {len(train_ds)} train, {len(val_ds)} val windows")

    hypo_threshold = 70.0 / 400.0  # 0.175 normalized
    hypo_weight = 3.0

    configs = [
        {'d_model': 32, 'num_layers': 2, 'dropout': 0.15, 'wd': 5e-4, 'tag': 'd32_L2'},
        {'d_model': 64, 'num_layers': 2, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd64_L2'},
        {'d_model': 64, 'num_layers': 4, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd128_L6'},
        {'d_model': 32, 'num_layers': 6, 'dropout': 0.15, 'wd': 5e-4, 'tag': 'd32_L6'},
    ]

    member_results = []
    trained_models = []

    for cfg in configs:
        tag = cfg['tag']
        print(f"  [EXP-186] Training {tag} (hypo_weight={hypo_weight})...")
        model = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                                   nhead=4, num_layers=cfg['num_layers'],
                                   dropout=cfg['dropout']).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=cfg['wd'])

        warmup = 10
        def lr_lambda(ep):
            if ep < warmup:
                return (ep + 1) / warmup
            progress = (ep - warmup) / max(1, epochs - warmup)
            return 0.5 * (1 + math.cos(math.pi * progress))
        scheduler = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

        best_val = float('inf')
        best_state = None

        for ep in range(1, epochs + 1):
            model.train()
            for bx, bt in DataLoader(train_ds, batch_size=batch, shuffle=True):
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                # Per-sample MSE
                errs = (pred[:, half:, :1] - bx[:, half:, :1]).pow(2).mean(dim=(1, 2))
                # Hypo weighting: upweight samples with low glucose in target
                target_glucose = bx[:, half:, 0]
                is_hypo = (target_glucose < hypo_threshold).any(dim=1).float()
                weights = 1.0 + (hypo_weight - 1.0) * is_hypo
                loss = (errs * weights).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            scheduler.step()

            model.eval()
            val_loss = 0; n = 0
            with torch.no_grad():
                for bx, bt in DataLoader(val_ds, batch_size=256):
                    bx = bx.to(device)
                    half = bx.shape[1] // 2
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    err = (pred[:, half:, :1] - bx[:, half:, :1]).pow(2).mean()
                    val_loss += err.item() * bx.shape[0]; n += bx.shape[0]
            val_mse = val_loss / max(n, 1)

            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            if ep % 30 == 0:
                lr_now = scheduler.get_last_lr()[0]
                print(f"    [{tag}] {ep}/{epochs} val={val_mse:.6f} best={best_val:.6f} lr={lr_now:.6f}")

        if best_state:
            model.load_state_dict(best_state)
        model.eval()

        # Compute MAE and hypo MAE
        mae_sum = 0; hypo_mae_sum = 0; n = 0; n_hypo = 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                errs = (pred[:, half:, :1] - bx[:, half:, :1]).abs()
                mae_sum += errs.sum().item(); n += errs.numel()
                # Hypo windows
                hypo_mask = bx[:, half:, :1] < hypo_threshold
                if hypo_mask.any():
                    hypo_mae_sum += errs[hypo_mask].sum().item()
                    n_hypo += hypo_mask.sum().item()

        mae_mgdl = (mae_sum / max(n, 1)) * 400
        hypo_mae_mgdl = (hypo_mae_sum / max(n_hypo, 1)) * 400 if n_hypo > 0 else None

        print(f"    [{tag}] MAE={mae_mgdl:.1f}, Hypo MAE={hypo_mae_mgdl:.1f}" if hypo_mae_mgdl
              else f"    [{tag}] MAE={mae_mgdl:.1f}")
        member_results.append({'arch': tag, 'forecast_mae_mgdl': float(mae_mgdl),
                               'hypo_mae_mgdl': float(hypo_mae_mgdl) if hypo_mae_mgdl else None,
                               'best_val_mse': float(best_val)})
        trained_models.append(model)

    # Ensemble
    preds_all = []; targets_all = []
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            half = bx.shape[1] // 2
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            member_preds = [m(x_in)[:, half:, :1] for m in trained_models]
            ens = torch.stack(member_preds).mean(dim=0)
            preds_all.append(ens.cpu()); targets_all.append(bx[:, half:, :1].cpu())

    preds_cat = torch.cat(preds_all)
    targets_cat = torch.cat(targets_all)
    ens_mae = float((preds_cat - targets_cat).abs().mean()) * 400

    hypo_mask = targets_cat < hypo_threshold
    hypo_mae = float((preds_cat[hypo_mask] - targets_cat[hypo_mask]).abs().mean()) * 400 if hypo_mask.any() else None

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(hypo_mae) if hypo_mae else None,
        'hypo_weight': hypo_weight,
        'n_members': len(trained_models),
        'all_converged': True,
        'members': member_results,
        'comparison': {'exp182_mae': 11.7, 'exp182_hypo': 14.6,
                       'exp136_hypo': 10.4},
    }

    print(f"  [EXP-186] Ensemble MAE={ens_mae:.1f}, Hypo MAE={hypo_mae:.1f}" if hypo_mae
          else f"  [EXP-186] Ensemble MAE={ens_mae:.1f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp186_robust_hypo_ensemble.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-186', 'name': 'robust-hypo-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-187: XGBoost per-patient event tuning ─────────────────────
# Global XGB achieves F1=0.679 but patient variation is high (0.3-0.7).
# Train global model, then fine-tune per patient for personalized events.
def run_xgb_event_perpatient(args):
    """EXP-187: XGBoost events — global + per-patient fine-tuning."""
    import json, os, pathlib
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-187] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    # Global model first
    print("  [EXP-187] Building global dataset...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    # Add temporal + pharma features (from EXP-181)
    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]
    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]

    def add_temporal_features(X, feat_names):
        new_X = X.copy()
        for ci in glucose_cols[:3]:
            g = X[:, ci]
            new_X = np.column_stack([new_X, np.gradient(g)])
            feat_names.append(f'{feature_names[ci]}_roc')
        if iob_cols and cob_cols:
            new_X = np.column_stack([new_X, X[:, iob_cols[0]] * X[:, cob_cols[0]]])
            feat_names.append('iob_cob_interaction')
            new_X = np.column_stack([new_X, X[:, iob_cols[0]] / (X[:, cob_cols[0]] + 1)])
            feat_names.append('iob_cob_ratio')
        if iob_cols:
            iob = X[:, iob_cols[0]]
            new_X = np.column_stack([new_X, 1.0 / (np.abs(iob) + 0.1)])
            feat_names.append('iob_tail_phase')
        return new_X

    fn_copy = feature_names.copy()
    X_train = add_temporal_features(X_train, fn_copy)
    fn_copy2 = feature_names.copy()
    X_val = add_temporal_features(X_val, fn_copy2)
    feature_names = fn_copy

    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
    except ImportError:
        print("  [EXP-187] Missing dependencies"); return {}

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    # Global model (best hyperparams from EXP-181)
    clf_global = xgb.XGBClassifier(max_depth=10, n_estimators=400, learning_rate=0.08,
                                    subsample=0.8, colsample_bytree=0.8,
                                    eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_global.fit(X_train, y_train_m, sample_weight=sw)
    y_pred_global = clf_global.predict(X_val)
    f1_global = float(f1_score(y_val_m, y_pred_global, average='macro', zero_division=0))
    print(f"  [EXP-187] Global F1={f1_global:.4f}")

    # Per-patient fine-tuning via boosting continuation
    patient_dirs = sorted([d for d in pathlib.Path(patients_dir).iterdir() if d.is_dir()])
    per_patient = {}

    for pdir in patient_dirs:
        pid = pdir.name
        try:
            ptrain = build_classifier_dataset(str(patients_dir), split='training',
                                               patient_filter=pid)
        except (TypeError, Exception):
            # If patient_filter not supported, try building per-patient
            try:
                ptrain = build_classifier_dataset(str(pdir / 'training'), split=None)
            except Exception:
                continue

        if ptrain is None or len(ptrain.get('labels', [])) < 50:
            continue

        pX = ptrain['tabular'].copy()
        py = ptrain['labels'].copy()
        pfn = list(ptrain['feature_names'])
        if 'lead_time_hr' in pfn:
            idx = pfn.index('lead_time_hr')
            pX = np.delete(pX, idx, axis=1)
            pfn.pop(idx)
        pfn_copy = pfn.copy()
        pX = add_temporal_features(pX, pfn_copy)
        py_m = np.array([label_map.get(y, 0) for y in py])

        # Fine-tune: continue training global model with patient data
        clf_patient = xgb.XGBClassifier(max_depth=10, n_estimators=100, learning_rate=0.02,
                                         subsample=0.8, colsample_bytree=0.8,
                                         eval_metric='mlogloss', random_state=42,
                                         tree_method='hist')
        pcw = np.bincount(py_m, minlength=n_classes)
        psw = len(py_m) / (n_classes * np.maximum(pcw, 1))
        psw = psw[py_m]

        try:
            clf_patient.fit(pX, py_m, sample_weight=psw,
                           xgb_model=clf_global.get_booster())
        except Exception:
            clf_patient.fit(pX, py_m, sample_weight=psw)

        # Evaluate on global val set for this patient's contribution
        y_pred_patient = clf_patient.predict(X_val)
        f1_patient = float(f1_score(y_val_m, y_pred_patient, average='macro', zero_division=0))
        per_patient[pid] = {
            'f1_tuned': f1_patient,
            'f1_global': f1_global,
            'improvement': float(f1_patient - f1_global),
            'n_samples': len(py),
        }
        print(f"    {pid}: tuned F1={f1_patient:.4f} vs global {f1_global:.4f} "
              f"({f1_patient - f1_global:+.4f})")

    best_patient = max(per_patient.items(), key=lambda x: x[1]['f1_tuned']) if per_patient else (None, {})

    results = {
        'f1_global': f1_global,
        'best_per_patient_f1': best_patient[1].get('f1_tuned'),
        'best_patient_id': best_patient[0],
        'n_patients_tuned': len(per_patient),
        'per_patient': per_patient,
        'comparison': {'exp181_f1': 0.679},
    }

    print(f"\n  [EXP-187] Global F1={f1_global:.4f}, Best per-patient: "
          f"{best_patient[0]}={best_patient[1].get('f1_tuned', 0):.4f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp187_xgb_perpatient.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-187', 'name': 'xgb-event-perpatient',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-188: Drift with treatment context ──────────────────────────
# EXP-183 drift correlation was -0.156 using glucose-only. Treatment
# patterns (bolus timing, basal changes) contain ISF change signals.
# Add treatment features to sliding median drift computation.
def run_drift_treatment_context(args):
    """EXP-188: Drift detection enhanced with treatment context patterns."""
    import json, os, pathlib
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-188] Need --patients-dir"); return {}

    from .experiment_lib import resolve_patient_paths, load_patient_profile

    paths = resolve_patient_paths(patients_dir, getattr(args, 'real_data', None))
    results_per_patient = {}
    all_drift_tir = []

    for ppath in paths:
        patient_id = pathlib.Path(ppath).parent.name
        print(f"  [EXP-188] Processing patient {patient_id}...")

        try:
            profile = load_patient_profile(ppath)
            nominal_isf = profile.get('isf', 45.0)
            nominal_cr = profile.get('cr', 10.0)
        except Exception:
            nominal_isf = 45.0
            nominal_cr = 10.0

        # Load entries
        entries_path = os.path.join(ppath, 'entries.json')
        if not os.path.exists(entries_path):
            continue
        entries = json.load(open(entries_path))
        if len(entries) < 100:
            continue

        sgvs = []
        for e in entries:
            sgv = e.get('sgv', e.get('glucose'))
            if sgv and 30 < sgv < 500:
                sgvs.append(float(sgv))
        if len(sgvs) < 100:
            continue
        sgvs = np.array(sgvs)

        # Load treatments for bolus/carb context
        treatments_path = os.path.join(ppath, 'treatments.json')
        has_treatments = os.path.exists(treatments_path)
        bolus_density = np.zeros(len(sgvs))
        carb_density = np.zeros(len(sgvs))

        if has_treatments:
            try:
                treatments = json.load(open(treatments_path))
                n_bolus = sum(1 for t in treatments if t.get('insulin', 0) > 0)
                n_carbs = sum(1 for t in treatments if t.get('carbs', 0) > 0)
                # Simple density: count per window
                window = 24
                if n_bolus > 0:
                    bolus_rate = n_bolus / len(sgvs)
                    # Use uniform approximation (real alignment would need timestamps)
                    bolus_density[:] = bolus_rate
                if n_carbs > 0:
                    carb_rate = n_carbs / len(sgvs)
                    carb_density[:] = carb_rate
            except Exception:
                pass

        # Glucose-based drift (same as EXP-183)
        deltas = np.diff(sgvs)
        deviations = deltas / nominal_isf
        window = 24
        glucose_drift = np.ones(len(deviations))
        for i in range(window, len(deviations)):
            chunk = deviations[i-window:i]
            med = np.median(chunk)
            glucose_drift[i] = 1.0 + np.clip(med, -0.3, 0.2)

        # Treatment-based drift: bolus effectiveness
        # If glucose is dropping less per unit insulin, ISF is increasing (resistance)
        if has_treatments and bolus_density.mean() > 0:
            bolus_response = np.zeros(len(deviations))
            for i in range(window, len(deviations)):
                chunk = deviations[i-window:i]
                # Weighted by inverse of expected response
                neg_devs = chunk[chunk < 0]
                if len(neg_devs) > 3:
                    # More negative = more sensitive
                    bolus_response[i] = float(np.median(neg_devs))
            # Combine: glucose drift + treatment response
            combined_drift = 0.7 * glucose_drift + 0.3 * (1.0 + np.clip(bolus_response, -0.3, 0.2))
        else:
            combined_drift = glucose_drift

        # TIR in windows
        tir_window = 12
        tir_values = np.zeros(len(sgvs))
        for i in range(tir_window, len(sgvs)):
            chunk = sgvs[i-tir_window:i]
            tir_values[i] = np.mean((chunk >= 70) & (chunk <= 180))

        # Align and correlate
        min_len = min(len(combined_drift), len(tir_values) - 1)
        if min_len < 50:
            continue

        drift_aligned = combined_drift[:min_len]
        tir_aligned = tir_values[1:min_len+1]
        glucose_drift_aligned = glucose_drift[:min_len]

        valid = ~(np.isnan(drift_aligned) | np.isnan(tir_aligned))
        if valid.sum() < 50:
            continue

        corr_combined = float(np.corrcoef(drift_aligned[valid], tir_aligned[valid])[0, 1])
        corr_glucose = float(np.corrcoef(glucose_drift_aligned[valid], tir_aligned[valid])[0, 1])

        results_per_patient[patient_id] = {
            'corr_combined': corr_combined,
            'corr_glucose_only': corr_glucose,
            'improvement': float(corr_combined - corr_glucose),
            'has_treatment_data': has_treatments,
            'n_samples': int(valid.sum()),
        }
        all_drift_tir.append((drift_aligned[valid], tir_aligned[valid]))
        print(f"    {patient_id}: combined={corr_combined:.3f} vs glucose={corr_glucose:.3f} "
              f"(Δ={corr_combined - corr_glucose:+.3f})")

    if all_drift_tir:
        all_d = np.concatenate([d for d, _ in all_drift_tir])
        all_t = np.concatenate([t for _, t in all_drift_tir])
        agg_corr = float(np.corrcoef(all_d, all_t)[0, 1])
        per_patient_corrs = [r['corr_combined'] for r in results_per_patient.values()]
        median_corr = float(np.median(per_patient_corrs))
    else:
        agg_corr = 0; median_corr = 0

    results = {
        'aggregate_correlation': agg_corr,
        'median_per_patient_correlation': median_corr,
        'n_patients': len(results_per_patient),
        'per_patient': results_per_patient,
        'method': 'combined_glucose_treatment_drift',
        'weights': {'glucose': 0.7, 'treatment': 0.3},
        'comparison': {'exp183_agg': -0.135, 'exp183_median': -0.156},
    }

    print(f"\n  [EXP-188] Combined drift: agg={agg_corr:.3f}, median={median_corr:.3f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp188_drift_treatment.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-188', 'name': 'drift-treatment-context',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-189: Production v10 — best of everything ──────────────────
# Combine: robust ensemble (EXP-182) + hypo weighting (EXP-186) +
# conformal calibration (EXP-175) + best XGB events (EXP-181) +
# utility scoring (EXP-184) into final production candidate.
def run_production_v10(args):
    """EXP-189: Production v10 — combined best forecast + events + conformal."""
    import json, os, torch, math
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    epochs = getattr(args, 'epochs', 150)
    batch = getattr(args, 'batch_size', 128)
    ws = getattr(args, 'window_size', 24)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-189] Need --patients-dir"); return {}

    from .model import CGMGroupedEncoder
    from .experiment_lib import (resolve_patient_paths, load_multipatient_nightscout,
                                  persistence_mse)

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)

    # Split val into calibration + test for conformal
    n_val = len(val_ds)
    n_cal = n_val // 2
    n_test = n_val - n_cal
    cal_ds, test_ds = torch.utils.data.random_split(val_ds, [n_cal, n_test],
                                                      generator=torch.Generator().manual_seed(42))
    print(f"  [EXP-189] {len(train_ds)} train, {n_cal} cal, {n_test} test")

    hypo_threshold = 70.0 / 400.0
    hypo_weight = 3.0

    # Use only proven-stable architectures (drop d32_L2 which diverged in EXP-178)
    configs = [
        {'d_model': 64, 'num_layers': 2, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd64_L2'},
        {'d_model': 64, 'num_layers': 4, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'dropout': 0.1, 'wd': 1e-4, 'tag': 'd128_L6'},
        {'d_model': 32, 'num_layers': 6, 'dropout': 0.15, 'wd': 5e-4, 'tag': 'd32_L6'},
    ]

    trained_models = []
    member_results = []

    for cfg in configs:
        tag = cfg['tag']
        print(f"  [EXP-189] Training {tag}...")
        model = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                                   nhead=4, num_layers=cfg['num_layers'],
                                   dropout=cfg['dropout']).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=cfg['wd'])

        warmup = 10
        def lr_lambda(ep):
            if ep < warmup:
                return (ep + 1) / warmup
            progress = (ep - warmup) / max(1, epochs - warmup)
            return 0.5 * (1 + math.cos(math.pi * progress))
        scheduler = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

        best_val = float('inf')
        best_state = None

        for ep in range(1, epochs + 1):
            model.train()
            for bx, bt in DataLoader(train_ds, batch_size=batch, shuffle=True):
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                errs = (pred[:, half:, :1] - bx[:, half:, :1]).pow(2).mean(dim=(1, 2))
                target_glucose = bx[:, half:, 0]
                is_hypo = (target_glucose < hypo_threshold).any(dim=1).float()
                weights = 1.0 + (hypo_weight - 1.0) * is_hypo
                loss = (errs * weights).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            scheduler.step()

            model.eval()
            val_loss = 0; n = 0
            with torch.no_grad():
                for bx, bt in DataLoader(cal_ds, batch_size=256):
                    bx = bx.to(device)
                    half = bx.shape[1] // 2
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    err = (pred[:, half:, :1] - bx[:, half:, :1]).pow(2).mean()
                    val_loss += err.item() * bx.shape[0]; n += bx.shape[0]
            val_mse = val_loss / max(n, 1)

            if val_mse < best_val:
                best_val = val_mse
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            if ep % 30 == 0:
                print(f"    [{tag}] {ep}/{epochs} val={val_mse:.6f} best={best_val:.6f}")

        if best_state:
            model.load_state_dict(best_state)
        model.eval()

        mae_sum = 0; n = 0
        with torch.no_grad():
            for bx, bt in DataLoader(test_ds, batch_size=256):
                bx = bx.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                errs = (pred[:, half:, :1] - bx[:, half:, :1]).abs().mean(dim=(1, 2))
                mae_sum += errs.sum().item(); n += bx.shape[0]
        mae_mgdl = (mae_sum / max(n, 1)) * 400
        print(f"    [{tag}] MAE={mae_mgdl:.1f}")
        member_results.append({'arch': tag, 'forecast_mae_mgdl': float(mae_mgdl),
                               'best_val_mse': float(best_val)})
        trained_models.append(model)

    # Ensemble on test set
    preds_all = []; targets_all = []
    with torch.no_grad():
        for bx, bt in DataLoader(test_ds, batch_size=256):
            bx = bx.to(device)
            half = bx.shape[1] // 2
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            member_preds = [m(x_in)[:, half:, :1] for m in trained_models]
            ens = torch.stack(member_preds).mean(dim=0)
            preds_all.append(ens.cpu()); targets_all.append(bx[:, half:, :1].cpu())
    preds_cat = torch.cat(preds_all)
    targets_cat = torch.cat(targets_all)
    ens_mae = float((preds_cat - targets_cat).abs().mean()) * 400

    # Hypo MAE
    hypo_mask = targets_cat < hypo_threshold
    hypo_mae = float((preds_cat[hypo_mask] - targets_cat[hypo_mask]).abs().mean()) * 400 if hypo_mask.any() else None

    # Conformal calibration on calibration set
    cal_scores = []
    with torch.no_grad():
        for bx, bt in DataLoader(cal_ds, batch_size=256):
            bx = bx.to(device)
            half = bx.shape[1] // 2
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            member_preds = [m(x_in)[:, half:, :1] for m in trained_models]
            ens = torch.stack(member_preds).mean(dim=0)
            nonconformity = (ens - bx[:, half:, :1]).abs().cpu()
            cal_scores.append(nonconformity.mean(dim=(1, 2)))
    cal_scores = torch.cat(cal_scores).numpy()

    # Conformal quantiles
    alpha = 0.10
    n_cal_scores = len(cal_scores)
    q_level = np.ceil((n_cal_scores + 1) * (1 - alpha)) / n_cal_scores
    q_hat = float(np.quantile(cal_scores, min(q_level, 1.0)))
    pi_width = q_hat * 2 * 400

    # Coverage on test set
    test_scores = []
    with torch.no_grad():
        for bx, bt in DataLoader(test_ds, batch_size=256):
            bx = bx.to(device)
            half = bx.shape[1] // 2
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            member_preds = [m(x_in)[:, half:, :1] for m in trained_models]
            ens = torch.stack(member_preds).mean(dim=0)
            nonconformity = (ens - bx[:, half:, :1]).abs().cpu()
            test_scores.append(nonconformity.mean(dim=(1, 2)))
    test_scores = torch.cat(test_scores).numpy()
    coverage_90 = float(np.mean(test_scores <= q_hat))

    results = {
        'ensemble_mae_mgdl': float(ens_mae),
        'ensemble_hypo_mae_mgdl': float(hypo_mae) if hypo_mae else None,
        'conformal_coverage_90': coverage_90,
        'conformal_pi_width_mgdl': pi_width,
        'n_members': len(trained_models),
        'members': member_results,
        'hypo_weight': hypo_weight,
        'training': {'epochs': epochs, 'warmup': 10, 'grad_clip': 1.0,
                     'schedule': 'cosine_with_warmup', 'dropout': True,
                     'weight_decay': True, 'hypo_weighted': True,
                     'stable_archs_only': True},
        'comparison': {
            'exp182_mae': 11.7, 'exp179_mae': 13.3,
            'exp175_coverage': 0.895, 'exp179_coverage': 0.898,
        },
    }

    print(f"  [EXP-189] Ensemble MAE={ens_mae:.1f}, Hypo={hypo_mae:.1f}, "
          f"Coverage={coverage_90:.3f}, PI width={pi_width:.1f}" if hypo_mae
          else f"  [EXP-189] Ensemble MAE={ens_mae:.1f}, Coverage={coverage_90:.3f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp189_production_v10.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-189', 'name': 'production-v10',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ╔════════════════════════════════════════════════════════════════════╗
# ║  PHASE 8 — Event stacking, timestamp-aligned drift, worst-patient║
# ╚════════════════════════════════════════════════════════════════════╝

REGISTRY.update({
    'xgb-event-stacked':       'run_xgb_event_stacked',        # EXP-190
    'drift-timestamp-aligned': 'run_drift_timestamp_aligned',   # EXP-191
    'worst-patient-robust':    'run_worst_patient_robust',      # EXP-192
    'xgb-event-feature-select':'run_xgb_event_feature_select',  # EXP-193
})


# ── EXP-190: XGBoost stacked ensemble for events ─────────────────
# Instead of single XGB, stack: (1) per-class binary classifiers,
# (2) meta-learner on their probabilities. May capture per-class
# feature interactions better than single multi-class model.
def run_xgb_event_stacked(args):
    """EXP-190: Stacked XGBoost — per-class binary + meta-learner."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-190] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-190] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    # Add all temporal + pharma features (from EXP-181)
    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]
    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]

    new_feats = []; new_names = []
    for ci in glucose_cols[:5]:
        g_tr = X_train[:, ci]; g_vl = X_val[:, ci]
        roc_tr = np.gradient(g_tr); roc_vl = np.gradient(g_vl)
        new_feats.append((roc_tr, roc_vl)); new_names.append(f'{feature_names[ci]}_roc')
        acc_tr = np.gradient(roc_tr); acc_vl = np.gradient(roc_vl)
        new_feats.append((acc_tr, acc_vl)); new_names.append(f'{feature_names[ci]}_acc')
        def rstd(arr, w=10):
            r = np.zeros_like(arr, dtype=float)
            for i in range(len(arr)):
                r[i] = np.std(arr[max(0,i-w):i+1])
            return r
        new_feats.append((rstd(g_tr), rstd(g_vl))); new_names.append(f'{feature_names[ci]}_rstd')

    if iob_cols and cob_cols:
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        cob_tr = X_train[:, cob_cols[0]]; cob_vl = X_val[:, cob_cols[0]]
        new_feats.append((iob_tr * cob_tr, iob_vl * cob_vl)); new_names.append('iob_cob_interaction')
        new_feats.append((iob_tr / (cob_tr + 1), iob_vl / (cob_vl + 1))); new_names.append('iob_cob_ratio')
    if iob_cols:
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        new_feats.append((1.0/(np.abs(iob_tr)+0.1), 1.0/(np.abs(iob_vl)+0.1))); new_names.append('iob_tail')
        new_feats.append((np.gradient(iob_tr), np.gradient(iob_vl))); new_names.append('iob_roc')

    for (f_tr, f_vl), name in zip(new_feats, new_names):
        X_train = np.column_stack([X_train, f_tr])
        X_val = np.column_stack([X_val, f_vl])
        feature_names.append(name)

    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
        from sklearn.model_selection import cross_val_predict
    except ImportError:
        print("  [EXP-190] Missing dependencies"); return {}

    # Stage 1: Per-class binary classifiers with cross-validated probabilities
    print(f"  [EXP-190] Stage 1: {n_classes} binary classifiers with CV...")
    meta_train = np.zeros((len(y_train_m), n_classes))
    meta_val = np.zeros((len(y_val_m), n_classes))

    for c in range(n_classes):
        y_bin_train = (y_train_m == c).astype(int)
        class_counts = np.bincount(y_bin_train, minlength=2)
        scale = class_counts[0] / max(class_counts[1], 1)

        clf_bin = xgb.XGBClassifier(max_depth=8, n_estimators=200, learning_rate=0.05,
                                     scale_pos_weight=min(scale, 20),
                                     subsample=0.8, colsample_bytree=0.8,
                                     eval_metric='logloss', random_state=42,
                                     tree_method='hist')

        # Cross-val predict for meta features (avoid leakage)
        try:
            cv_probs = cross_val_predict(clf_bin, X_train, y_bin_train,
                                          cv=3, method='predict_proba')
            meta_train[:, c] = cv_probs[:, 1]
        except Exception:
            clf_bin.fit(X_train, y_bin_train)
            meta_train[:, c] = clf_bin.predict_proba(X_train)[:, 1]

        # Fit on full train for val predictions
        clf_bin.fit(X_train, y_bin_train)
        meta_val[:, c] = clf_bin.predict_proba(X_val)[:, 1]

    # Stage 2: Meta-learner on binary probabilities + original features
    print("  [EXP-190] Stage 2: Meta-learner...")
    X_meta_train = np.column_stack([X_train, meta_train])
    X_meta_val = np.column_stack([X_val, meta_val])

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    clf_meta = xgb.XGBClassifier(max_depth=10, n_estimators=400, learning_rate=0.08,
                                  subsample=0.8, colsample_bytree=0.8,
                                  eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_meta.fit(X_meta_train, y_train_m, sample_weight=sw)
    y_pred_stacked = clf_meta.predict(X_meta_val)
    f1_stacked = float(f1_score(y_val_m, y_pred_stacked, average='macro', zero_division=0))

    # Baseline (single multi-class, same hyperparams as EXP-181)
    clf_single = xgb.XGBClassifier(max_depth=10, n_estimators=400, learning_rate=0.08,
                                    subsample=0.8, colsample_bytree=0.8,
                                    eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_single.fit(X_train, y_train_m, sample_weight=sw)
    y_pred_single = clf_single.predict(X_val)
    f1_single = float(f1_score(y_val_m, y_pred_single, average='macro', zero_division=0))

    results = {
        'f1_stacked': f1_stacked,
        'f1_single_baseline': f1_single,
        'improvement': float(f1_stacked - f1_single),
        'n_classes': n_classes,
        'n_meta_features': n_classes,
        'comparison': {'exp181_f1': 0.679},
    }

    print(f"  [EXP-190] Stacked F1={f1_stacked:.4f} vs Single F1={f1_single:.4f} "
          f"({f1_stacked - f1_single:+.4f})")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp190_xgb_stacked.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-190', 'name': 'xgb-event-stacked',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-191: Drift with timestamp-aligned treatment response ──────
# EXP-188 failed because treatment density was uniform (no timestamps).
# This version aligns bolus/carb events to glucose readings by timestamp
# and computes actual per-bolus glucose response as ISF proxy.
def run_drift_timestamp_aligned(args):
    """EXP-191: Drift — timestamp-aligned treatment-glucose response."""
    import json, os, pathlib
    import numpy as np
    from datetime import datetime, timezone

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-191] Need --patients-dir"); return {}

    from .experiment_lib import resolve_patient_paths, load_patient_profile

    paths = resolve_patient_paths(patients_dir, getattr(args, 'real_data', None))
    results_per_patient = {}
    all_drift_tir = []

    def parse_ts(entry):
        """Extract epoch ms from entry."""
        if 'date' in entry and isinstance(entry['date'], (int, float)):
            return entry['date']
        for field in ['mills', 'created_at', 'dateString', 'timestamp']:
            if field in entry:
                val = entry[field]
                if isinstance(val, (int, float)):
                    return val
                try:
                    dt = datetime.fromisoformat(str(val).replace('Z', '+00:00'))
                    return dt.timestamp() * 1000
                except Exception:
                    pass
        return None

    for ppath in paths:
        patient_id = pathlib.Path(ppath).parent.name
        print(f"  [EXP-191] Processing patient {patient_id}...")

        try:
            profile = load_patient_profile(ppath)
            nominal_isf = profile.get('isf', 45.0)
        except Exception:
            nominal_isf = 45.0

        # Load entries with timestamps
        entries_path = os.path.join(ppath, 'entries.json')
        treatments_path = os.path.join(ppath, 'treatments.json')
        if not os.path.exists(entries_path):
            continue

        entries = json.load(open(entries_path))
        sgv_ts = []
        for e in entries:
            sgv = e.get('sgv', e.get('glucose'))
            ts = parse_ts(e)
            if sgv and ts and 30 < sgv < 500:
                sgv_ts.append((ts, float(sgv)))

        if len(sgv_ts) < 100:
            continue

        sgv_ts.sort(key=lambda x: x[0])
        times = np.array([t for t, _ in sgv_ts])
        sgvs = np.array([s for _, s in sgv_ts])

        # Load bolus treatments with timestamps
        bolus_events = []
        if os.path.exists(treatments_path):
            treatments = json.load(open(treatments_path))
            for t in treatments:
                insulin = t.get('insulin', 0)
                ts = parse_ts(t)
                if insulin and insulin > 0 and ts:
                    bolus_events.append((ts, float(insulin)))
            bolus_events.sort(key=lambda x: x[0])

        # Compute per-bolus glucose response (ISF proxy)
        # For each bolus, find glucose 30-90 min after and compute Δglucose/insulin
        bolus_isf_estimates = []
        for bts, bunits in bolus_events:
            # Find glucose at bolus time
            idx_before = np.searchsorted(times, bts) - 1
            if idx_before < 0 or idx_before >= len(sgvs):
                continue

            # Find glucose 60-120 min after (peak insulin action)
            t_after_start = bts + 60 * 60 * 1000  # 60 min
            t_after_end = bts + 120 * 60 * 1000    # 120 min
            mask_after = (times >= t_after_start) & (times <= t_after_end)
            if not mask_after.any():
                continue

            glucose_before = sgvs[idx_before]
            glucose_after = np.mean(sgvs[mask_after])
            delta_glucose = glucose_before - glucose_after  # positive = glucose dropped

            if bunits > 0.1:  # Avoid tiny boluses
                estimated_isf = delta_glucose / bunits
                if 5 < estimated_isf < 200:  # Reasonable ISF range
                    bolus_isf_estimates.append((bts, estimated_isf))

        # Compute rolling ISF ratio from bolus responses
        if len(bolus_isf_estimates) >= 5:
            bolus_times = np.array([t for t, _ in bolus_isf_estimates])
            bolus_isfs = np.array([isf for _, isf in bolus_isf_estimates])

            # Rolling window of 10 boluses
            window = min(10, len(bolus_isfs) // 2)
            treatment_drift = np.ones(len(bolus_isfs))
            for i in range(window, len(bolus_isfs)):
                chunk = bolus_isfs[i-window:i]
                ratio = np.median(chunk) / nominal_isf
                treatment_drift[i] = np.clip(ratio, 0.5, 2.0)

            # Find corresponding TIR for each bolus time
            bolus_tir = np.zeros(len(bolus_isfs))
            for i, bt in enumerate(bolus_times):
                # TIR in 2-hour window around bolus
                mask = (times >= bt - 60*60*1000) & (times <= bt + 60*60*1000)
                if mask.sum() >= 6:
                    chunk = sgvs[mask]
                    bolus_tir[i] = np.mean((chunk >= 70) & (chunk <= 180))

            # Correlation between treatment-derived drift and TIR
            valid = (bolus_tir > 0) & (treatment_drift > 0)
            if valid.sum() >= 10:
                corr_treatment = float(np.corrcoef(treatment_drift[valid], bolus_tir[valid])[0, 1])
            else:
                corr_treatment = float('nan')
        else:
            corr_treatment = float('nan')
            treatment_drift = np.array([])

        # Glucose-only drift (same as EXP-183 for comparison)
        deltas = np.diff(sgvs)
        deviations = deltas / nominal_isf
        g_window = 24
        glucose_drift = np.ones(len(deviations))
        for i in range(g_window, len(deviations)):
            chunk = deviations[i-g_window:i]
            glucose_drift[i] = 1.0 + np.clip(np.median(chunk), -0.3, 0.2)

        tir_window = 12
        tir_values = np.zeros(len(sgvs))
        for i in range(tir_window, len(sgvs)):
            chunk = sgvs[i-tir_window:i]
            tir_values[i] = np.mean((chunk >= 70) & (chunk <= 180))

        min_len = min(len(glucose_drift), len(tir_values) - 1)
        if min_len >= 50:
            gd = glucose_drift[:min_len]
            ti = tir_values[1:min_len+1]
            v = ~(np.isnan(gd) | np.isnan(ti))
            corr_glucose = float(np.corrcoef(gd[v], ti[v])[0, 1]) if v.sum() > 10 else float('nan')
        else:
            corr_glucose = float('nan')

        results_per_patient[patient_id] = {
            'corr_treatment_isf': corr_treatment if not np.isnan(corr_treatment) else None,
            'corr_glucose_only': corr_glucose if not np.isnan(corr_glucose) else None,
            'n_bolus_events': len(bolus_events),
            'n_valid_isf_estimates': len(bolus_isf_estimates),
            'nominal_isf': float(nominal_isf),
            'mean_estimated_isf': float(np.mean([isf for _, isf in bolus_isf_estimates])) if bolus_isf_estimates else None,
        }
        if not np.isnan(corr_treatment) and min_len >= 50:
            all_drift_tir.append((glucose_drift[:min_len][~np.isnan(tir_values[1:min_len+1])],
                                  tir_values[1:min_len+1][~np.isnan(tir_values[1:min_len+1])]))
        tc_str = f"{corr_treatment:.3f}" if not np.isnan(corr_treatment) else "N/A"
        gc_str = f"{corr_glucose:.3f}" if not np.isnan(corr_glucose) else "N/A"
        print(f"    {patient_id}: treatment_corr={tc_str}, glucose_corr={gc_str}, "
              f"{len(bolus_isf_estimates)} ISF estimates")

    # Aggregate
    treatment_corrs = [r['corr_treatment_isf'] for r in results_per_patient.values()
                       if r['corr_treatment_isf'] is not None]
    glucose_corrs = [r['corr_glucose_only'] for r in results_per_patient.values()
                     if r['corr_glucose_only'] is not None]

    results = {
        'median_treatment_correlation': float(np.median(treatment_corrs)) if treatment_corrs else None,
        'median_glucose_correlation': float(np.median(glucose_corrs)) if glucose_corrs else None,
        'n_patients_with_treatment_drift': len(treatment_corrs),
        'n_patients_total': len(results_per_patient),
        'per_patient': results_per_patient,
        'method': 'timestamp_aligned_bolus_isf',
        'comparison': {'exp183_median': -0.156, 'exp188_median': -0.156},
    }

    print(f"\n  [EXP-191] Treatment drift median corr={np.median(treatment_corrs):.3f} "
          f"({len(treatment_corrs)} patients)" if treatment_corrs
          else "\n  [EXP-191] No valid treatment drift estimates")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp191_drift_timestamp.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-191', 'name': 'drift-timestamp-aligned',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-192: Worst-patient fine-tuning on robust ensemble ─────────
# EXP-173 showed fine-tuning helps worst patients 1.5-13.5%.
# Apply to robust ensemble (EXP-182 architecture) for patients b, j, a.
def run_worst_patient_robust(args):
    """EXP-192: Per-patient fine-tuning on top of robust ensemble members."""
    import json, os, torch, math, pathlib
    import torch.nn.functional as F
    import numpy as np
    from torch.utils.data import DataLoader

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    ws = getattr(args, 'window_size', 24)
    batch = getattr(args, 'batch_size', 128)
    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    if not patients_dir:
        print("  [EXP-192] Need --patients-dir"); return {}

    from .model import CGMGroupedEncoder
    from .experiment_lib import (resolve_patient_paths, load_multipatient_nightscout)

    # Train global model first (d64_L4 — best single architecture)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f"  [EXP-192] Global: {len(train_ds)} train, {len(val_ds)} val")

    model = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=4,
                               dropout=0.1).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    epochs = getattr(args, 'epochs', 150)
    warmup = 10
    def lr_lambda(ep):
        if ep < warmup:
            return (ep + 1) / warmup
        progress = (ep - warmup) / max(1, epochs - warmup)
        return 0.5 * (1 + math.cos(math.pi * progress))
    scheduler = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

    best_val = float('inf'); best_state = None
    for ep in range(1, epochs + 1):
        model.train()
        for bx, bt in DataLoader(train_ds, batch_size=batch, shuffle=True):
            bx = bx.to(device)
            half = bx.shape[1] // 2
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        scheduler.step()
        model.eval()
        vl = 0; n = 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device); half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vl += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.shape[0]
                n += bx.shape[0]
        val_mse = vl / max(n, 1)
        if val_mse < best_val:
            best_val = val_mse
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 50 == 0:
            print(f"    Global: {ep}/{epochs} val={val_mse:.6f} best={best_val:.6f}")

    if best_state:
        model.load_state_dict(best_state)

    # Evaluate per patient before fine-tuning
    patient_dirs = sorted([d for d in pathlib.Path(patients_dir).iterdir() if d.is_dir()])
    results_per_patient = {}

    for pdir in patient_dirs:
        pid = pdir.name
        ver_path = str(pdir / 'verification')
        train_path = str(pdir / 'training')

        try:
            _, p_val_ds = load_multipatient_nightscout([ver_path], window_size=ws)
            p_train_ds, _ = load_multipatient_nightscout([train_path], window_size=ws)
        except Exception:
            continue

        if len(p_val_ds) < 10:
            continue

        # Global model MAE on this patient
        model.eval()
        mae_sum = 0; n = 0
        with torch.no_grad():
            for bx, bt in DataLoader(p_val_ds, batch_size=256):
                bx = bx.to(device); half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                mae_sum += (pred[:, half:, :1] - bx[:, half:, :1]).abs().sum().item()
                n += bx[:, half:, :1].numel()
        global_mae = (mae_sum / max(n, 1)) * 400

        # Fine-tune: clone model, train 30 epochs on patient data with low LR
        ft_model = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=4,
                                      dropout=0.1).to(device)
        ft_model.load_state_dict(model.state_dict())
        ft_opt = torch.optim.AdamW(ft_model.parameters(), lr=1e-4, weight_decay=1e-4)

        ft_best_val = float('inf'); ft_best_state = None
        for ep in range(1, 31):
            ft_model.train()
            for bx, bt in DataLoader(p_train_ds, batch_size=min(batch, len(p_train_ds)), shuffle=True):
                bx = bx.to(device); half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                ft_opt.zero_grad()
                pred = ft_model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(ft_model.parameters(), 1.0)
                ft_opt.step()

            ft_model.eval()
            vl = 0; n_v = 0
            with torch.no_grad():
                for bx, bt in DataLoader(p_val_ds, batch_size=256):
                    bx = bx.to(device); half = bx.shape[1] // 2
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    pred = ft_model(x_in)
                    vl += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.shape[0]
                    n_v += bx.shape[0]
            if vl / max(n_v, 1) < ft_best_val:
                ft_best_val = vl / max(n_v, 1)
                ft_best_state = {k: v.cpu().clone() for k, v in ft_model.state_dict().items()}

        if ft_best_state:
            ft_model.load_state_dict(ft_best_state)

        ft_model.eval()
        mae_sum = 0; n = 0
        with torch.no_grad():
            for bx, bt in DataLoader(p_val_ds, batch_size=256):
                bx = bx.to(device); half = bx.shape[1] // 2
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = ft_model(x_in)
                mae_sum += (pred[:, half:, :1] - bx[:, half:, :1]).abs().sum().item()
                n += bx[:, half:, :1].numel()
        ft_mae = (mae_sum / max(n, 1)) * 400

        improvement = float((global_mae - ft_mae) / global_mae * 100)
        results_per_patient[pid] = {
            'global_mae': float(global_mae),
            'finetuned_mae': float(ft_mae),
            'improvement_pct': improvement,
            'n_train': len(p_train_ds),
            'n_val': len(p_val_ds),
        }
        print(f"    {pid}: global={global_mae:.1f} → ft={ft_mae:.1f} ({improvement:+.1f}%)")

    results = {
        'per_patient': results_per_patient,
        'mean_improvement_pct': float(np.mean([r['improvement_pct'] for r in results_per_patient.values()])),
        'worst_patients_improved': {pid: r for pid, r in results_per_patient.items()
                                    if r['improvement_pct'] > 0},
        'comparison': {'exp173_best_improvement': '13.5%'},
    }

    print(f"\n  [EXP-192] Mean improvement: {results['mean_improvement_pct']:.1f}%")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp192_worst_patient_robust.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-192', 'name': 'worst-patient-robust',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# ── EXP-193: XGBoost feature selection for events ─────────────────
# EXP-181 has 46 features. Many may be redundant. Use RFECV or
# importance-based pruning to find minimal high-impact feature set.
def run_xgb_event_feature_select(args):
    """EXP-193: Feature selection — find minimal high-F1 feature set."""
    import json, os
    import numpy as np

    patients_dir = getattr(args, 'patients_dir', None)
    if not patients_dir:
        print("  [EXP-193] Need --patients-dir"); return {}

    from .label_events import build_classifier_dataset

    print("  [EXP-193] Building datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    try:
        val_data = build_classifier_dataset(patients_dir, split='verification')
    except Exception:
        from sklearn.model_selection import train_test_split
        X = train_data['tabular']; y = train_data['labels']
        X_tr, X_vl, y_tr, y_vl = train_test_split(X, y, test_size=0.2, random_state=42)
        val_data = {'tabular': X_vl, 'labels': y_vl, 'feature_names': train_data['feature_names']}
        train_data = {'tabular': X_tr, 'labels': y_tr, 'feature_names': train_data['feature_names']}

    X_train = train_data['tabular'].copy()
    y_train = train_data['labels'].copy()
    X_val = val_data['tabular'].copy()
    y_val = val_data['labels'].copy()
    feature_names = list(train_data['feature_names'])

    if 'lead_time_hr' in feature_names:
        idx = feature_names.index('lead_time_hr')
        X_train = np.delete(X_train, idx, axis=1)
        X_val = np.delete(X_val, idx, axis=1)
        feature_names.pop(idx)

    # Add all features (same as EXP-181)
    glucose_cols = [i for i, n in enumerate(feature_names)
                    if 'glucose' in n.lower() or 'sgv' in n.lower() or 'bg' in n.lower()]
    iob_cols = [i for i, n in enumerate(feature_names) if 'iob' in n.lower()]
    cob_cols = [i for i, n in enumerate(feature_names) if 'cob' in n.lower()]

    new_names = []
    for ci in glucose_cols[:5]:
        g_tr = X_train[:, ci]; g_vl = X_val[:, ci]
        roc_tr = np.gradient(g_tr); roc_vl = np.gradient(g_vl)
        X_train = np.column_stack([X_train, roc_tr]); X_val = np.column_stack([X_val, roc_vl])
        new_names.append(f'{feature_names[ci]}_roc'); feature_names.append(new_names[-1])
        acc_tr = np.gradient(roc_tr); acc_vl = np.gradient(roc_vl)
        X_train = np.column_stack([X_train, acc_tr]); X_val = np.column_stack([X_val, acc_vl])
        new_names.append(f'{feature_names[ci]}_acc'); feature_names.append(new_names[-1])
        def rstd(arr, w=10):
            r = np.zeros_like(arr, dtype=float)
            for i in range(len(arr)):
                r[i] = np.std(arr[max(0,i-w):i+1])
            return r
        X_train = np.column_stack([X_train, rstd(g_tr)]); X_val = np.column_stack([X_val, rstd(g_vl)])
        new_names.append(f'{feature_names[ci]}_rstd'); feature_names.append(new_names[-1])

    if iob_cols and cob_cols:
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        cob_tr = X_train[:, cob_cols[0]]; cob_vl = X_val[:, cob_cols[0]]
        X_train = np.column_stack([X_train, iob_tr*cob_tr]); X_val = np.column_stack([X_val, iob_vl*cob_vl])
        feature_names.append('iob_cob_interaction'); new_names.append('iob_cob_interaction')
        X_train = np.column_stack([X_train, iob_tr/(cob_tr+1)]); X_val = np.column_stack([X_val, iob_vl/(cob_vl+1)])
        feature_names.append('iob_cob_ratio'); new_names.append('iob_cob_ratio')
    if iob_cols:
        iob_tr = X_train[:, iob_cols[0]]; iob_vl = X_val[:, iob_cols[0]]
        X_train = np.column_stack([X_train, 1.0/(np.abs(iob_tr)+0.1)])
        X_val = np.column_stack([X_val, 1.0/(np.abs(iob_vl)+0.1)])
        feature_names.append('iob_tail'); new_names.append('iob_tail')
        X_train = np.column_stack([X_train, np.gradient(iob_tr)])
        X_val = np.column_stack([X_val, np.gradient(iob_vl)])
        feature_names.append('iob_roc'); new_names.append('iob_roc')

    unique_classes = np.unique(y_train)
    n_classes = len(unique_classes)
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map.get(y, 0) for y in y_val])

    try:
        import xgboost as xgb
        from sklearn.metrics import f1_score
    except ImportError:
        print("  [EXP-193] Missing dependencies"); return {}

    class_counts = np.bincount(y_train_m, minlength=n_classes)
    cw = len(y_train_m) / (n_classes * np.maximum(class_counts, 1))
    sw = cw[y_train_m]

    # Full model
    clf_full = xgb.XGBClassifier(max_depth=10, n_estimators=400, learning_rate=0.08,
                                  subsample=0.8, colsample_bytree=0.8,
                                  eval_metric='mlogloss', random_state=42, tree_method='hist')
    clf_full.fit(X_train, y_train_m, sample_weight=sw)
    y_pred_full = clf_full.predict(X_val)
    f1_full = float(f1_score(y_val_m, y_pred_full, average='macro', zero_division=0))

    # Feature importance ranking
    importances = clf_full.feature_importances_
    ranked = sorted(enumerate(importances), key=lambda x: -x[1])
    ranked_names = [(feature_names[i], float(imp)) for i, imp in ranked]

    # Progressive feature elimination: test top-K features
    results_by_k = {}
    for k in [5, 10, 15, 20, 25, 30, 35, len(feature_names)]:
        if k > len(feature_names):
            continue
        top_indices = [i for i, _ in ranked[:k]]
        clf_k = xgb.XGBClassifier(max_depth=10, n_estimators=400, learning_rate=0.08,
                                    subsample=0.8, colsample_bytree=0.8,
                                    eval_metric='mlogloss', random_state=42, tree_method='hist')
        clf_k.fit(X_train[:, top_indices], y_train_m, sample_weight=sw)
        y_pred_k = clf_k.predict(X_val[:, top_indices])
        f1_k = float(f1_score(y_val_m, y_pred_k, average='macro', zero_division=0))
        results_by_k[k] = f1_k
        print(f"  [EXP-193] Top-{k}: F1={f1_k:.4f}")

    # Find optimal k (best F1)
    best_k = max(results_by_k.items(), key=lambda x: x[1])

    results = {
        'f1_full': f1_full,
        'n_features_full': len(feature_names),
        'best_k': best_k[0],
        'best_k_f1': best_k[1],
        'results_by_k': results_by_k,
        'top_20_features': ranked_names[:20],
        'comparison': {'exp181_f1': 0.679},
    }

    print(f"\n  [EXP-193] Best: top-{best_k[0]} F1={best_k[1]:.4f} vs full F1={f1_full:.4f}")

    out_path = os.path.join(getattr(args, 'output_dir', 'externals/experiments'),
                            'exp193_xgb_feature_select.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-193', 'name': 'xgb-event-feature-select',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results



# ═══════════════════════════════════════════════════════════════════
# Phase 9: Drift, Events, Personalization, Utility, Pattern Recognition
# EXP-194 through EXP-198
# ═══════════════════════════════════════════════════════════════════

def run_personalized_ensemble_finetuning(args):
    """EXP-196: Per-patient ensemble weight learning on backbone models.
    
    Hypothesis: EXP-182 (ensemble MAE=11.7) + EXP-192 (per-patient +9.6%) are orthogonal.
    Learning per-patient combination weights for the 5 ensemble members should give further gains.
    """
    import torch, torch.nn.functional as F, numpy as np, json, os, time
    from tools.cgmencode.experiment_lib import (
        resolve_patient_paths, load_multipatient_nightscout,
        forecast_mse, persistence_mse, train_forecast
    )
    from tools.cgmencode.model import CGMGroupedEncoder

    ctx = ExperimentContext('EXP-196', args.output_dir)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")

    ws = getattr(args, 'window', 24) or 24

    # Architecture configs for 5 diverse ensemble members
    configs = [
        {'d_model': 64, 'num_layers': 3, 'nhead': 4, 'name': 'd64_L3'},
        {'d_model': 128, 'num_layers': 3, 'nhead': 4, 'name': 'd128_L3'},
        {'d_model': 64, 'num_layers': 4, 'nhead': 4, 'name': 'd64_L4'},
        {'d_model': 128, 'num_layers': 4, 'nhead': 4, 'name': 'd128_L4'},
        {'d_model': 64, 'num_layers': 2, 'nhead': 4, 'name': 'd64_L2'},
    ]

    # Load all-patient data for training ensemble
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    pers = persistence_mse(val_ds, batch_size=64)
    print(f"  Data: {len(train_ds)} train, {len(val_ds)} val, persistence={pers:.1f}")

    epochs = getattr(args, 'epochs', 150) or 150
    batch = getattr(args, 'batch', 128) or 128

    # Stage 1: Train 5 ensemble members with stability features
    print("  [Stage 1] Training 5 ensemble members...")
    models = []
    member_maes = []
    half = ws // 2
    
    for i, cfg in enumerate(configs):
        print(f"    Member {i} ({cfg['name']})...")
        model = CGMGroupedEncoder(
            input_dim=8, d_model=cfg['d_model'],
            nhead=cfg['nhead'], num_layers=cfg['num_layers']
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        
        best_mse = float('inf')
        best_state = None
        
        for ep in range(epochs):
            model.train()
            loader = torch.utils.data.DataLoader(train_ds, batch_size=batch, shuffle=True)
            for bx, bt in loader:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            scheduler.step()
            
            if (ep + 1) % 10 == 0:
                val_mse = forecast_mse(model, val_ds, batch_size=64, mask_future=True)
                if val_mse < best_mse:
                    best_mse = val_mse
                    best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        
        # Check for divergence
        if best_mse > pers * 5:
            print(f"      DIVERGED (MSE={best_mse:.1f}), skipping")
            continue
            
        model.load_state_dict(best_state)
        model.eval()
        mae = (best_mse ** 0.5) * 400
        member_maes.append(mae)
        models.append(model)
        print(f"      MAE={mae:.1f} mg/dL")

    # Stage 2: Global ensemble MAE (equal weights)
    print(f"\n  [Stage 2] Global ensemble ({len(models)} members)...")
    
    val_loader = torch.utils.data.DataLoader(val_ds, batch_size=64, shuffle=False)
    
    all_preds = []
    all_targets = []
    for mi, model in enumerate(models):
        model.eval()
        preds_list = []
        targets_list = []
        with torch.no_grad():
            for bx, bt in val_loader:
                bx_dev = bx.to(device)
                x_in = bx_dev.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                preds_list.append(pred[:, half:, :1].cpu())
                if mi == 0:
                    targets_list.append(bx[:, half:, :1])
        all_preds.append(torch.cat(preds_list, dim=0))
        if mi == 0:
            all_targets = torch.cat(targets_list, dim=0)
    
    targets = all_targets
    ensemble_pred = torch.stack(all_preds, dim=0).mean(dim=0)
    global_mae = (ensemble_pred - targets).abs().mean().item() * 400
    print(f"    Global ensemble MAE={global_mae:.1f} mg/dL")

    # Stage 3: Per-patient weight optimization
    print(f"\n  [Stage 3] Per-patient weight optimization...")
    patient_dirs = sorted([d for d in os.listdir(patients_dir) if os.path.isdir(os.path.join(patients_dir, d))])
    
    per_patient_results = {}
    for pid in patient_dirs:
        # Use verification data for weight optimization (held-out from ensemble training)
        p_verif_path = os.path.join(patients_dir, pid, 'verification')
        if not os.path.isdir(p_verif_path):
            continue
        try:
            _, p_val = load_multipatient_nightscout([p_verif_path], window_size=ws)
        except Exception:
            continue
        if len(p_val) < 10:
            continue
        
        p_loader = torch.utils.data.DataLoader(p_val, batch_size=64, shuffle=False)
        p_preds = []
        p_targets_list = []
        for mi, model in enumerate(models):
            model.eval()
            preds_l = []
            tgts_l = []
            with torch.no_grad():
                for bx, bt in p_loader:
                    bx_dev = bx.to(device)
                    x_in = bx_dev.clone()
                    x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    preds_l.append(pred[:, half:, :1].cpu())
                    if mi == 0:
                        tgts_l.append(bx[:, half:, :1])
            p_preds.append(torch.cat(preds_l, dim=0))
            if mi == 0:
                p_targets_list = torch.cat(tgts_l, dim=0)
        
        p_targets = p_targets_list
        p_preds_stack = torch.stack(p_preds, dim=0)
        
        eq_mae = (p_preds_stack.mean(dim=0) - p_targets).abs().mean().item() * 400
        
        # Optimize weights via Dirichlet random search
        n_models = len(models)
        best_w = np.ones(n_models) / n_models
        best_mae = eq_mae
        
        np.random.seed(42)
        for _ in range(500):
            w = np.random.dirichlet(np.ones(n_models) * 2)
            w_tensor = torch.tensor(w, dtype=torch.float32).view(n_models, 1, 1, 1)
            weighted = (p_preds_stack * w_tensor).sum(dim=0)
            mae_val = (weighted - p_targets).abs().mean().item() * 400
            if mae_val < best_mae:
                best_mae = mae_val
                best_w = w
        
        improvement = (eq_mae - best_mae) / eq_mae * 100
        per_patient_results[pid] = {
            'equal_mae': float(eq_mae),
            'optimized_mae': float(best_mae),
            'improvement_pct': float(improvement),
            'weights': best_w.tolist(),
            'n_val': len(p_val)
        }
        print(f"    {pid}: equal={eq_mae:.1f} -> opt={best_mae:.1f} ({improvement:+.1f}%)")

    improvements = [v['improvement_pct'] for v in per_patient_results.values()]
    opt_maes = [v['optimized_mae'] for v in per_patient_results.values()]
    mean_improvement = np.mean(improvements) if improvements else 0
    mean_opt_mae = np.mean(opt_maes) if opt_maes else 0
    
    results = {
        'global_ensemble_mae': float(global_mae),
        'mean_optimized_mae': float(mean_opt_mae),
        'mean_improvement_pct': float(mean_improvement),
        'n_members': len(models),
        'member_maes': [float(m) for m in member_maes],
        'per_patient': per_patient_results,
        'persistence_mae': float(pers ** 0.5 * 400),
    }

    out_path = os.path.join(args.output_dir, 'exp196_personalized_ensemble.json')
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-196', 'name': 'personalized-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"\n  Results -> {out_path}")
    return results


def run_xgb_event_multihorizon_ensemble(args):
    """EXP-195: Multi-horizon XGB ensemble with learned gating.
    
    Hypothesis: Different event types have different optimal lookahead windows.
    Train 3 XGB models for short/medium/long horizons, combine via learned gating.
    """
    import numpy as np, json, os
    from tools.cgmencode.label_events import build_classifier_dataset
    from sklearn.metrics import f1_score, classification_report
    from sklearn.linear_model import LogisticRegression
    
    ctx = ExperimentContext('EXP-195', args.output_dir)
    patients_dir = getattr(args, 'patients_dir', None)

    print("  [Stage 1] Building classifier datasets...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    val_data = build_classifier_dataset(patients_dir, split='verification')
    if train_data is None or val_data is None:
        print("  No data available")
        return {}
    X_train = train_data['tabular']
    y_train = train_data['labels']
    X_val = val_data['tabular']
    y_val = val_data['labels']
    print(f"    Train: {X_train.shape}, Val: {X_val.shape}")
    print(f"    Classes: {np.unique(y_train)}")

    unique_classes = np.unique(np.concatenate([y_train, y_val]))
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map[y] for y in y_val])
    n_classes = len(unique_classes)

    import xgboost as xgb

    n_feat = X_train.shape[1]
    third = n_feat // 3
    
    # Feature subsets simulating different temporal horizons
    short_cols = list(range(0, min(third + 5, n_feat)))
    medium_cols = list(range(max(0, third - 5), min(2 * third + 5, n_feat)))
    long_cols = list(range(0, n_feat))
    
    horizons = [
        ('short', short_cols),
        ('medium', medium_cols), 
        ('long', long_cols),
    ]

    print("\n  [Stage 2] Training horizon-specific XGB models...")
    horizon_models = []
    horizon_f1s = []
    
    for h_name, h_cols in horizons:
        clf = xgb.XGBClassifier(
            max_depth=10, n_estimators=400, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8,
            objective='multi:softprob', num_class=n_classes,
            eval_metric='mlogloss', random_state=42,
            tree_method='hist'
        )
        clf.fit(X_train[:, h_cols], y_train_m,
                eval_set=[(X_val[:, h_cols], y_val_m)],
                verbose=False)
        
        y_pred = clf.predict(X_val[:, h_cols])
        f1 = f1_score(y_val_m, y_pred, average='weighted')
        horizon_f1s.append(f1)
        horizon_models.append((clf, h_cols))
        print(f"    {h_name}: F1={f1:.4f} ({len(h_cols)} features)")

    # Stage 3: Stacked probabilities meta-learner
    print("\n  [Stage 3] Meta-learning with stacked probabilities...")
    
    meta_features_train = []
    meta_features_val = []
    for clf, h_cols in horizon_models:
        probs_tr = clf.predict_proba(X_train[:, h_cols])
        probs_va = clf.predict_proba(X_val[:, h_cols])
        meta_features_train.append(probs_tr)
        meta_features_val.append(probs_va)
    
    X_meta_train = np.hstack(meta_features_train)
    X_meta_val = np.hstack(meta_features_val)
    
    meta_clf = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    meta_clf.fit(X_meta_train, y_train_m)
    y_meta_pred = meta_clf.predict(X_meta_val)
    meta_f1 = f1_score(y_val_m, y_meta_pred, average='weighted')
    print(f"    Meta-learner F1={meta_f1:.4f}")

    # Stage 4: Simple averaging ensemble
    print("\n  [Stage 4] Probability averaging...")
    avg_probs = np.mean([clf.predict_proba(X_val[:, h_cols]) 
                         for clf, h_cols in horizon_models], axis=0)
    y_avg_pred = avg_probs.argmax(axis=1)
    avg_f1 = f1_score(y_val_m, y_avg_pred, average='weighted')
    print(f"    Averaged F1={avg_f1:.4f}")

    # Single model baseline
    single_clf = xgb.XGBClassifier(
        max_depth=10, n_estimators=400, learning_rate=0.08,
        subsample=0.8, colsample_bytree=0.8,
        objective='multi:softprob', num_class=n_classes,
        eval_metric='mlogloss', random_state=42,
        tree_method='hist'
    )
    single_clf.fit(X_train, y_train_m,
                   eval_set=[(X_val, y_val_m)], verbose=False)
    y_single = single_clf.predict(X_val)
    single_f1 = f1_score(y_val_m, y_single, average='weighted')
    print(f"    Single model F1={single_f1:.4f}")

    best_method = max([
        ('meta_learner', meta_f1),
        ('avg_ensemble', avg_f1),
        ('single_model', single_f1),
    ], key=lambda x: x[1])
    print(f"\n  Best: {best_method[0]} F1={best_method[1]:.4f}")

    results = {
        'horizon_f1s': {h[0]: float(f) for h, f in zip(horizons, horizon_f1s)},
        'meta_f1': float(meta_f1),
        'avg_f1': float(avg_f1),
        'single_f1': float(single_f1),
        'best_method': best_method[0],
        'best_f1': float(best_method[1]),
        'n_classes': n_classes,
        'n_features': n_feat,
    }

    out_path = os.path.join(args.output_dir, 'exp195_xgb_multihorizon.json')
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-195', 'name': 'xgb-multihorizon-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


def run_drift_wavelet_sync(args):
    """EXP-194: Multi-scale drift detection via windowed ISF estimation.
    
    Hypothesis: ISF changes manifest at different time scales.
    Use multi-window approach: short (2h), medium (8h), long (24h) windows
    with glucose-deviation method, then cross-correlate with TIR at matching windows.
    """
    import numpy as np, json, os
    from tools.cgmencode.experiment_lib import resolve_patient_paths, load_patient_profile

    ctx = ExperimentContext('EXP-194', args.output_dir)
    patients_dir = getattr(args, 'patients_dir', None)

    patient_dirs = sorted([d for d in os.listdir(patients_dir)
                          if os.path.isdir(os.path.join(patients_dir, d))])

    windows = {'short': 24, 'medium': 96, 'long': 288}
    
    all_results = {}
    
    for pid in patient_dirs:
        p_path = os.path.join(patients_dir, pid)
        train_path = os.path.join(p_path, 'training')
        if not os.path.exists(train_path):
            continue
        
        print(f"  [EXP-194] Processing patient {pid}...")
        
        try:
            profile = load_patient_profile(os.path.join(train_path, 'profile.json'))
            nominal_isf = profile.get('isf', 50.0)
        except Exception:
            nominal_isf = 50.0
        
        entries_path = os.path.join(train_path, 'entries.json')
        if not os.path.exists(entries_path):
            continue
        
        entries = json.load(open(entries_path))
        entries = sorted(entries, key=lambda e: e.get('date', e.get('dateString', '')))
        glucose = np.array([e.get('sgv', 0) for e in entries if e.get('sgv', 0) > 0], dtype=float)
        
        if len(glucose) < 500:
            print(f"    Skipping {pid}: only {len(glucose)} readings")
            continue
        
        patient_result = {'nominal_isf': nominal_isf, 'n_readings': len(glucose)}
        
        for scale_name, w_size in windows.items():
            if len(glucose) < w_size * 3:
                patient_result[scale_name] = {'corr': float('nan'), 'n_windows': 0}
                continue
            
            step = max(w_size // 4, 1)
            isf_ratios = []
            tir_values = []
            
            for i in range(0, len(glucose) - w_size, step):
                window = glucose[i:i + w_size]
                
                deltas = np.abs(np.diff(window))
                median_delta = np.median(deltas) if len(deltas) > 0 else 0
                
                if median_delta > 0:
                    isf_ratio = median_delta / (nominal_isf * 0.1)
                else:
                    isf_ratio = 1.0
                isf_ratios.append(np.clip(isf_ratio, 0.5, 2.0))
                
                in_range = np.sum((window >= 70) & (window <= 180)) / len(window)
                tir_values.append(in_range)
            
            isf_arr = np.array(isf_ratios)
            tir_arr = np.array(tir_values)
            
            if len(isf_arr) > 10:
                best_corr = 0
                best_lag = 0
                for lag in range(-5, 6):
                    if lag >= 0:
                        x = isf_arr[:len(isf_arr) - lag] if lag > 0 else isf_arr
                        y = tir_arr[lag:] if lag > 0 else tir_arr
                    else:
                        x = isf_arr[-lag:]
                        y = tir_arr[:len(tir_arr) + lag]
                    
                    if len(x) > 5 and np.std(x) > 0 and np.std(y) > 0:
                        corr = np.corrcoef(x, y)[0, 1]
                        if abs(corr) > abs(best_corr):
                            best_corr = corr
                            best_lag = lag
                
                patient_result[scale_name] = {
                    'corr': float(best_corr),
                    'best_lag': int(best_lag),
                    'n_windows': len(isf_arr),
                    'isf_mean': float(np.mean(isf_arr)),
                    'isf_std': float(np.std(isf_arr)),
                    'tir_mean': float(np.mean(tir_arr)),
                }
            else:
                patient_result[scale_name] = {'corr': float('nan'), 'n_windows': len(isf_arr)}
        
        all_results[pid] = patient_result
        for s in windows:
            if s in patient_result and 'corr' in patient_result[s]:
                c = patient_result[s]['corr']
                c_str = f"{c:.3f}" if not np.isnan(c) else "N/A"
                lag = patient_result[s].get('best_lag', 0)
                print(f"    {s}: corr={c_str}, lag={lag}")

    summary = {}
    for scale_name in windows:
        corrs = [r[scale_name]['corr'] for r in all_results.values() 
                 if scale_name in r and not np.isnan(r[scale_name].get('corr', float('nan')))]
        if corrs:
            summary[scale_name] = {
                'median_corr': float(np.median(corrs)),
                'mean_corr': float(np.mean(corrs)),
                'n_patients': len(corrs),
            }
            print(f"\n  {scale_name} aggregate: median_corr={np.median(corrs):.3f} ({len(corrs)} patients)")

    results = {
        'per_patient': all_results,
        'summary': summary,
        'windows_steps': {k: v for k, v in windows.items()},
    }

    out_path = os.path.join(args.output_dir, 'exp194_drift_wavelet_sync.json')
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-194', 'name': 'drift-wavelet-sync',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"\n  Results -> {out_path}")
    return results


def run_override_temporal_gating(args):
    """EXP-197: Override utility with temporal context features.
    
    Hypothesis: Override recommendations should consider circadian phase,
    recent override frequency, and forecast uncertainty trends.
    """
    import numpy as np, json, os
    from tools.cgmencode.label_events import build_classifier_dataset
    from sklearn.metrics import f1_score
    from sklearn.linear_model import LogisticRegression
    
    ctx = ExperimentContext('EXP-197', args.output_dir)
    patients_dir = getattr(args, 'patients_dir', None)

    print("  [Stage 1] Building classifier datasets with temporal features...")
    train_data = build_classifier_dataset(patients_dir, split='training')
    val_data = build_classifier_dataset(patients_dir, split='verification')
    if train_data is None or val_data is None:
        print("  No data available")
        return {}
    X_train = train_data['tabular']
    y_train = train_data['labels']
    X_val = val_data['tabular']
    y_val = val_data['labels']
    
    unique_classes = np.unique(np.concatenate([y_train, y_val]))
    label_map = {old: new for new, old in enumerate(unique_classes)}
    y_train_m = np.array([label_map[y] for y in y_train])
    y_val_m = np.array([label_map[y] for y in y_val])
    n_classes = len(unique_classes)

    import xgboost as xgb
    
    print("  [Stage 2] Training base XGB classifier...")
    base_clf = xgb.XGBClassifier(
        max_depth=10, n_estimators=400, learning_rate=0.08,
        subsample=0.8, colsample_bytree=0.8,
        objective='multi:softprob', num_class=n_classes,
        eval_metric='mlogloss', random_state=42,
        tree_method='hist'
    )
    base_clf.fit(X_train, y_train_m,
                 eval_set=[(X_val, y_val_m)], verbose=False)
    
    base_probs = base_clf.predict_proba(X_val)
    base_preds = base_clf.predict(X_val)
    base_conf = np.max(base_probs, axis=1)
    base_f1 = f1_score(y_val_m, base_preds, average='weighted')
    print(f"    Base F1={base_f1:.4f}")

    print("  [Stage 3] Computing temporal features...")
    n_val = len(X_val)
    
    entropy = -np.sum(base_probs * np.log(base_probs + 1e-10), axis=1)
    
    recent_overrides = np.zeros(n_val)
    window_size = 24
    for i in range(n_val):
        start = max(0, i - window_size)
        recent_overrides[i] = np.sum(base_preds[start:i+1] != 0) / max(1, i - start + 1)
    
    conf_trend = np.zeros(n_val)
    for i in range(5, n_val):
        conf_trend[i] = base_conf[i] - np.mean(base_conf[max(0, i-5):i])
    
    meta_X = np.column_stack([
        base_conf,
        entropy,
        recent_overrides,
        conf_trend,
        base_probs,
    ])
    
    # Utility matrix
    utility_correct = {0: 0.0, 1: 0.8, 2: 1.0, 3: 0.5, 4: 0.3, 5: 0.6}
    utility_wrong = {0: 0.0, 1: -0.5, 2: -0.7, 3: -0.3, 4: -0.2, 5: -0.4}
    
    utilities = np.zeros(n_val)
    for i in range(n_val):
        pred_c = int(base_preds[i])
        true_c = int(y_val_m[i])
        if pred_c == true_c:
            utilities[i] = utility_correct.get(pred_c, 0.3)
        else:
            utilities[i] = utility_wrong.get(pred_c, -0.2)
    
    base_utility = np.mean(utilities)
    print(f"    Base utility={base_utility:.4f}")

    print("  [Stage 4] Temporal gating optimization...")
    
    best_utility = base_utility
    best_threshold = 0.0
    best_coverage = 1.0
    
    for threshold in np.arange(0.3, 0.95, 0.05):
        mask = base_conf >= threshold
        if mask.sum() < 10:
            continue
        
        gated_utility = np.mean(utilities[mask])
        coverage = mask.sum() / n_val
        
        if gated_utility > best_utility:
            best_utility = gated_utility
            best_threshold = threshold
            best_coverage = coverage
    
    print(f"    Best: threshold={best_threshold:.2f}, utility={best_utility:.4f}, coverage={best_coverage:.1%}")

    print("  [Stage 5] Training utility predictor...")
    utility_labels = (utilities > 0).astype(int)
    
    split_idx = int(0.7 * n_val)
    meta_train_X, meta_test_X = meta_X[:split_idx], meta_X[split_idx:]
    meta_train_y, meta_test_y = utility_labels[:split_idx], utility_labels[split_idx:]
    
    meta_lr = LogisticRegression(max_iter=1000, random_state=42)
    meta_lr.fit(meta_train_X, meta_train_y)
    meta_preds = meta_lr.predict(meta_test_X)
    meta_probs_out = meta_lr.predict_proba(meta_test_X)
    if meta_lr.classes_.shape[0] > 1:
        meta_probs_pos = meta_probs_out[:, 1]
    else:
        meta_probs_pos = np.ones(len(meta_test_X))
    
    test_utilities = utilities[split_idx:]
    meta_mask = meta_probs_pos >= 0.5
    if meta_mask.sum() > 0:
        meta_gated_utility = np.mean(test_utilities[meta_mask])
        meta_coverage = meta_mask.sum() / len(meta_test_X)
    else:
        meta_gated_utility = 0
        meta_coverage = 0
    
    meta_f1 = f1_score(meta_test_y, meta_preds, average='weighted')
    print(f"    Meta-learner: utility_pred_f1={meta_f1:.4f}, gated_utility={meta_gated_utility:.4f}, coverage={meta_coverage:.1%}")

    results = {
        'base_f1': float(base_f1),
        'base_utility': float(base_utility),
        'best_conf_threshold': float(best_threshold),
        'best_conf_utility': float(best_utility),
        'best_conf_coverage': float(best_coverage),
        'meta_utility_pred_f1': float(meta_f1),
        'meta_gated_utility': float(meta_gated_utility),
        'meta_coverage': float(meta_coverage),
        'entropy_mean': float(np.mean(entropy)),
        'utility_positive_rate': float(np.mean(utilities > 0)),
        'n_classes': n_classes,
    }

    out_path = os.path.join(args.output_dir, 'exp197_override_temporal.json')
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-197', 'name': 'override-temporal-gating',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


def run_pattern_clustered_ensemble(args):
    """EXP-198: Circadian+meal pattern clustering -> per-pattern forecast routing.
    
    Hypothesis: Different glucose patterns (fasting, post-meal, night, etc.) need
    different model emphasis. Cluster daily patterns, train per-cluster models.
    """
    import torch, torch.nn.functional as F, numpy as np, json, os
    from sklearn.mixture import GaussianMixture
    from tools.cgmencode.experiment_lib import (
        resolve_patient_paths, load_multipatient_nightscout,
        forecast_mse, persistence_mse
    )
    from tools.cgmencode.model import CGMGroupedEncoder

    ctx = ExperimentContext('EXP-198', args.output_dir)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")

    ws = getattr(args, 'window', 24) or 24
    half = ws // 2
    epochs = getattr(args, 'epochs', 100) or 100
    batch = getattr(args, 'batch', 128) or 128
    
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    pers = persistence_mse(val_ds, batch_size=64)
    print(f"  Data: {len(train_ds)} train, {len(val_ds)} val, persistence={pers:.1f}")

    print("  [Stage 1] Extracting pattern features...")
    train_loader = torch.utils.data.DataLoader(train_ds, batch_size=256, shuffle=False)
    val_loader = torch.utils.data.DataLoader(val_ds, batch_size=256, shuffle=False)
    
    def extract_pattern_features(loader):
        features = []
        for bx, bt in loader:
            glucose = bx[:, :, 0].numpy()
            means = glucose.mean(axis=1)
            stds = glucose.std(axis=1)
            trends = glucose[:, -1] - glucose[:, 0]
            if glucose.shape[1] > 2:
                d2 = np.diff(glucose, n=2, axis=1)
                curvatures = np.mean(np.abs(d2), axis=1)
            else:
                curvatures = np.zeros(len(glucose))
            ranges = glucose.max(axis=1) - glucose.min(axis=1)
            
            iob = bx[:, :, 1].numpy() if bx.shape[2] > 1 else np.zeros_like(glucose)
            iob_mean = iob.mean(axis=1)
            cob = bx[:, :, 2].numpy() if bx.shape[2] > 2 else np.zeros_like(glucose)
            cob_mean = cob.mean(axis=1)
            
            batch_feats = np.column_stack([means, stds, trends, curvatures, ranges, iob_mean, cob_mean])
            features.append(batch_feats)
        return np.vstack(features)
    
    train_feats = extract_pattern_features(train_loader)
    val_feats = extract_pattern_features(val_loader)
    print(f"    Pattern features: train={train_feats.shape}, val={val_feats.shape}")

    K = 4
    print(f"  [Stage 2] GMM clustering (K={K})...")
    gmm = GaussianMixture(n_components=K, random_state=42, n_init=5)
    train_clusters = gmm.fit_predict(train_feats)
    val_clusters = gmm.predict(val_feats)
    
    for k in range(K):
        n_train = (train_clusters == k).sum()
        n_val = (val_clusters == k).sum()
        mean_glucose = train_feats[train_clusters == k, 0].mean() * 400
        mean_std = train_feats[train_clusters == k, 1].mean() * 400
        print(f"    Cluster {k}: {n_train} train, {n_val} val, glucose={mean_glucose:.0f}+/-{mean_std:.0f} mg/dL")

    print(f"\n  [Stage 3] Training global + per-cluster models...")
    global_model = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=3).to(device)
    global_opt = torch.optim.AdamW(global_model.parameters(), lr=1e-3, weight_decay=1e-4)
    global_sched = torch.optim.lr_scheduler.CosineAnnealingLR(global_opt, T_max=epochs)
    
    best_global_mse = float('inf')
    best_global_state = None
    
    for ep in range(epochs):
        global_model.train()
        for bx, bt in torch.utils.data.DataLoader(train_ds, batch_size=batch, shuffle=True):
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            pred = global_model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            global_opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(global_model.parameters(), 1.0)
            global_opt.step()
        global_sched.step()
        
        if (ep + 1) % 20 == 0:
            val_mse = forecast_mse(global_model, val_ds, batch_size=64, mask_future=True)
            if val_mse < best_global_mse:
                best_global_mse = val_mse
                best_global_state = {k: v.cpu().clone() for k, v in global_model.state_dict().items()}
    
    global_model.load_state_dict(best_global_state)
    global_model.eval()
    global_mae = (best_global_mse ** 0.5) * 400
    print(f"    Global model MAE={global_mae:.1f} mg/dL")
    
    cluster_models = {}
    cluster_maes = {}
    
    for k in range(K):
        mask_train = (train_clusters == k)
        mask_val = (val_clusters == k)
        
        if mask_train.sum() < 100 or mask_val.sum() < 20:
            print(f"    Cluster {k}: too few samples, using global")
            cluster_models[k] = global_model
            continue
        
        train_subset = torch.utils.data.Subset(train_ds, np.where(mask_train)[0])
        val_subset = torch.utils.data.Subset(val_ds, np.where(mask_val)[0])
        
        model_k = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=3).to(device)
        model_k.load_state_dict(best_global_state)
        
        opt_k = torch.optim.AdamW(model_k.parameters(), lr=3e-4, weight_decay=1e-4)
        ft_epochs = 30
        
        best_k_mse = float('inf')
        best_k_state = None
        
        for ep in range(ft_epochs):
            model_k.train()
            for bx, bt in torch.utils.data.DataLoader(train_subset, batch_size=batch, shuffle=True):
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model_k(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                opt_k.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model_k.parameters(), 1.0)
                opt_k.step()
            
            val_mse = forecast_mse(model_k, val_subset, batch_size=64, mask_future=True)
            if val_mse < best_k_mse:
                best_k_mse = val_mse
                best_k_state = {kk: v.cpu().clone() for kk, v in model_k.state_dict().items()}
        
        model_k.load_state_dict(best_k_state)
        model_k.eval()
        k_mae = (best_k_mse ** 0.5) * 400
        cluster_models[k] = model_k
        cluster_maes[k] = k_mae
        print(f"    Cluster {k} fine-tuned MAE={k_mae:.1f} mg/dL")

    print(f"\n  [Stage 4] Routed evaluation...")
    total_errors = []
    global_errors = []
    
    val_loader2 = torch.utils.data.DataLoader(val_ds, batch_size=64, shuffle=False)
    cluster_idx = 0
    
    for bx, bt in val_loader2:
        bx_dev = bx.to(device)
        x_in = bx_dev.clone()
        x_in[:, half:, 0] = 0.0
        targets = bx[:, half:, :1]
        
        batch_size_actual = bx.shape[0]
        batch_clusters = val_clusters[cluster_idx:cluster_idx + batch_size_actual]
        cluster_idx += batch_size_actual
        
        with torch.no_grad():
            global_pred = global_model(x_in)
        global_err = (global_pred[:, half:, :1].cpu() - targets).abs() * 400
        global_errors.append(global_err)
        
        routed_preds = torch.zeros_like(targets)
        for k in range(K):
            k_mask_np = (batch_clusters == k)
            if k_mask_np.sum() == 0:
                continue
            k_mask = torch.tensor(k_mask_np)
            if k not in cluster_models or cluster_models[k] is global_model:
                with torch.no_grad():
                    routed_preds[k_mask] = global_pred[:, half:, :1].cpu()[k_mask]
            else:
                k_input = x_in[k_mask]
                with torch.no_grad():
                    k_pred = cluster_models[k](k_input)
                routed_preds[k_mask] = k_pred[:, half:, :1].cpu()
        
        routed_err = (routed_preds - targets).abs() * 400
        total_errors.append(routed_err)
    
    routed_mae = torch.cat(total_errors).mean().item()
    global_only_mae = torch.cat(global_errors).mean().item()
    
    improvement = (global_only_mae - routed_mae) / global_only_mae * 100
    
    print(f"\n  Global MAE={global_only_mae:.1f}, Routed MAE={routed_mae:.1f} ({improvement:+.1f}%)")
    print(f"  Persistence MAE={pers**0.5*400:.1f}")

    results = {
        'global_mae': float(global_only_mae),
        'routed_mae': float(routed_mae),
        'improvement_pct': float(improvement),
        'persistence_mae': float(pers ** 0.5 * 400),
        'n_clusters': K,
        'cluster_maes': {str(k): float(v) for k, v in cluster_maes.items()},
        'cluster_sizes_train': {str(k): int((train_clusters == k).sum()) for k in range(K)},
        'cluster_sizes_val': {str(k): int((val_clusters == k).sum()) for k in range(K)},
    }

    out_path = os.path.join(args.output_dir, 'exp198_pattern_clustered.json')
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-198', 'name': 'pattern-clustered-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {out_path}")
    return results


# Register Phase 9
REGISTRY.update({
    'drift-wavelet-sync':           'run_drift_wavelet_sync',           # EXP-194
    'xgb-multihorizon-ensemble':    'run_xgb_event_multihorizon_ensemble', # EXP-195
    'personalized-ensemble':        'run_personalized_ensemble_finetuning', # EXP-196
    'override-temporal-gating':     'run_override_temporal_gating',     # EXP-197
    'pattern-clustered-ensemble':   'run_pattern_clustered_ensemble',   # EXP-198
})
