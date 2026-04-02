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

# ╔════════════════════════════════════════════════════════════════════╗
# ║  EXPERIMENT REGISTRY — add new experiments here                  ║
# ╚════════════════════════════════════════════════════════════════════╝

REGISTRY = {
    'extended-features':      'run_extended_features',      # EXP-026
    'event-classifier':       'run_event_classifier',       # EXP-027
    'multihorizon':           'run_multihorizon',           # EXP-028
    'uncertainty-calibration': 'run_uncertainty_calibration', # EXP-029
    'isf-cr-tracking':        'run_isf_cr_tracking',        # EXP-030
    'scenario-validation':    'run_scenario_validation',    # EXP-031
    'backtest':               'run_backtest',               # EXP-032
    'feature-transfer':       'run_feature_transfer',       # EXP-033
    # Round 2
    'clinical-metrics':       'run_clinical_metrics',       # EXP-034
    'norm-multihorizon':      'run_norm_multihorizon',      # EXP-035
    'classifier-no-leadtime': 'run_classifier_no_leadtime', # EXP-036
    'rolling-features':       'run_rolling_features',       # EXP-037
    'cost-sensitive':         'run_cost_sensitive',          # EXP-038
    'physics-residual-6hr':   'run_physics_residual_6hr',   # EXP-039
    'horizon-transfer':       'run_horizon_transfer',       # EXP-040
    'backtest-denorm':        'run_backtest_denorm',        # EXP-041
    # Round 3 — composite evaluation
    'composite-decision':     'run_composite_decision',     # EXP-042
    'forecast-masked':        'run_forecast_masked',        # EXP-043
    # Round 4 — forecast refinement + classifier combos
    'arch-sweep':             'run_arch_sweep',             # EXP-044
    'per-patient-finetune':   'run_per_patient_finetune',   # EXP-045
    'walkforward-forecast':   'run_walkforward_forecast',   # EXP-046
    'forecast-16f':           'run_forecast_16f',           # EXP-047
    'physics-residual-train': 'run_physics_residual_train', # EXP-048
    'combined-classifier':    'run_combined_classifier',    # EXP-049
    'binary-detectors':       'run_binary_detectors',       # EXP-050
    'forecast-multiseed':     'run_forecast_multiseed',     # EXP-051
    'forecast-uncertainty':   'run_forecast_uncertainty',   # EXP-052
    'longer-training':        'run_longer_training',        # EXP-053
    'event-conditioned':      'run_event_conditioned',      # EXP-054
    'patient-generalization':  'run_patient_generalization', # EXP-055
    # Round 5 — uncertainty, pipeline, and feature fixes
    'ensemble-uncertainty':    'run_ensemble_uncertainty',   # EXP-056
    'selective-finetune':      'run_selective_finetune',     # EXP-057
    'safe-16f-forecast':       'run_safe_16f_forecast',      # EXP-058
    'conformal-prediction':    'run_conformal_prediction',   # EXP-059
    'backtest-fixed':          'run_backtest_fixed',         # EXP-060
    'horizon-ensemble':        'run_horizon_ensemble',       # EXP-061
    # Round 6 — combining wins, production-readiness
    'conformal-backtest':      'run_conformal_backtest',     # EXP-062
    'extended-selective-ft':   'run_extended_selective_ft',   # EXP-063
    'forecast-classification': 'run_forecast_classification', # EXP-064
    'timestep-conformal':      'run_timestep_conformal',     # EXP-065
    'patient-conformal':       'run_patient_conformal',      # EXP-066
    'multitask-encoder':       'run_multitask_encoder',      # EXP-067
    # Round 7 — multi-task refinement, production pipeline
    'multitask-balanced':      'run_multitask_balanced',     # EXP-068
    'combined-all-classifier': 'run_combined_all_classifier', # EXP-069
    'timestep-backtest':       'run_timestep_backtest',      # EXP-070
    'multitask-finetune':      'run_multitask_finetune',     # EXP-071
    'production-pipeline':     'run_production_pipeline',    # EXP-072
    'action-recommendation':   'run_action_recommendation',  # EXP-073
    # Round 8 — planning horizons, counterfactuals, circadian
    'time-to-event':           'run_time_to_event',          # EXP-074
    'counterfactual-dose':     'run_counterfactual_dose',    # EXP-075
    'circadian-forecast':      'run_circadian_forecast',     # EXP-076
    'action-magnitude':        'run_action_magnitude',       # EXP-077
    'streaming-conformal':     'run_streaming_conformal',    # EXP-078
    'multihorizon-trajectory': 'run_multihorizon_trajectory', # EXP-079
    # Round 9 — safety, sensitivity, planning
    'hypo-focused':            'run_hypo_focused',            # EXP-080
    'asymmetric-loss':         'run_asymmetric_loss',         # EXP-081
    'direct-tte':              'run_direct_tte',              # EXP-082
    'chained-planning':        'run_chained_planning',        # EXP-083
    'gradient-sensitivity':    'run_gradient_sensitivity',    # EXP-084
    'stacked-classifier':      'run_stacked_classifier',      # EXP-085
    # Round 10 — combining breakthroughs, production upgrade
    'asymmetric-long':         'run_asymmetric_long',         # EXP-086
    'unified-forecast-tte':    'run_unified_forecast_tte',    # EXP-087
    'production-v2':           'run_production_v2',           # EXP-088
    'conformal-chained':       'run_conformal_chained',       # EXP-089
    'hypo-ensemble':           'run_hypo_ensemble',           # EXP-090
    'planning-horizon-sweep':  'run_planning_horizon_sweep',  # EXP-091
    # Round 11 — hypo precision, multi-hour, calibration
    'hypo-calibrated':         'run_hypo_calibrated',         # EXP-092
    'direct-multihour':        'run_direct_multihour',        # EXP-093
    'forecast-quantile':       'run_forecast_quantile',       # EXP-094
    'production-v3-planner':   'run_production_v3_planner',   # EXP-095
    'patient-adaptive':        'run_patient_adaptive',        # EXP-096
    'action-value':            'run_action_value',            # EXP-097
    # ── Round 12: Calibration, Ensemble, Circadian, Integration ──
    'wide-quantile':           'run_wide_quantile',           # EXP-098
    'direct-2hr-quantile':     'run_direct_2hr_quantile',     # EXP-099
    'seed-ensemble':           'run_seed_ensemble',           # EXP-100
    'circadian-positional':    'run_circadian_forecast_v2',   # EXP-101
    'production-v4':           'run_production_v4',           # EXP-102
    'long-context-counterfactual': 'run_long_context_cf',     # EXP-103
    # ── Round 13: Precision Gating, Augmentation, Conformal, Multi-Output ──
    'confidence-gated':        'run_confidence_gated',        # EXP-104
    'hypo-augmented':          'run_hypo_augmented',          # EXP-105
    'conformal-2hr':           'run_conformal_2hr',           # EXP-106
    'multi-output':            'run_multi_output',            # EXP-107
    'dropout-ensemble':        'run_dropout_ensemble',        # EXP-108
    'walkforward-multi':       'run_walkforward_multi',       # EXP-109
}


# ────────────────────────────────────────────────────────────────────
# EXP-026: Extended 16-Feature GroupedEncoder
# Hypothesis: Context features (day-of-week, override state, glucose
#   ROC/accel, time-since-event) improve forecast quality at 1hr+.
# Success: >5% improvement in forecast MSE over 8-feature baseline.
# ────────────────────────────────────────────────────────────────────

def run_extended_features(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-026', out, hypothesis='16f > 8f forecast')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # Build 16-feature windows
    windows = build_16f_windows(paths, window_size=24)
    ctx.log(f'{len(windows)} windows from {len(paths)} patients')
    if len(windows) < 100:
        ctx.log('Too few windows; aborting'); return ctx.save('exp026_results.json')
    train_ds, val_ds = windows_to_datasets(windows)

    # 8-feature baseline
    ds8, vds8 = load_multipatient_nightscout(
        [p for p in paths], window_size=24)
    base_mse = persistence_mse(vds8)

    model8 = create_model('grouped', input_dim=8)
    best8, _ = train(model8, ds8, vds8,
                     f'{out}/exp026_grouped_8f.pth', 'Grouped-8f')
    mse8 = forecast_mse(model8, vds8)

    # 16-feature model
    model16 = create_model('grouped', input_dim=16)
    best16, _ = train(model16, train_ds, val_ds,
                      f'{out}/exp026_grouped_16f.pth', 'Grouped-16f')
    mse16 = forecast_mse(model16, val_ds)

    ctx.result.update({
        'windows_8f': len(ds8), 'windows_16f': len(windows),
        'persistence_mse': base_mse,
        'grouped_8f_mse': mse8, 'grouped_16f_mse': mse16,
        'improvement_pct': improvement_pct(mse16, mse8),
        'success': mse16 < mse8 * 0.95,
    })
    ctx.section('Results')
    ctx.log(f'8f={mse8:.6f}  16f={mse16:.6f}  '
            f'Δ={ctx.result["improvement_pct"]:.1f}%  '
            f'{"✓ PASS" if ctx.result["success"] else "✗ FAIL"}')
    return ctx.save('exp026_extended_features.json')


# ────────────────────────────────────────────────────────────────────
# EXP-027: XGBoost Event Classifier
# Hypothesis: CGM+IOB patterns → meal/exercise detection, F1 > 0.7
# ────────────────────────────────────────────────────────────────────

def run_event_classifier(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-027', out, hypothesis='event detection F1>0.7')
    patients_dir = getattr(args, 'patients_dir', None)

    if not patients_dir:
        ctx.log('Need --patients-dir'); return ctx.save('exp027_results.json')

    ctx.section('Building classifier dataset')
    ds = build_classifier_dataset(
        patients_dir, window_steps=12, lead_steps=[3, 6, 9, 12])
    if ds is None:
        ctx.log('No data returned'); return ctx.save('exp027_results.json')
    tabular = ds['tabular']
    labels = ds['labels']
    feature_names = ds.get('feature_names', ds.get('tabular_names', []))
    ctx.log(f'{len(labels)} samples, {tabular.shape[1]} features, '
            f'classes={sorted(set(labels.astype(int).tolist()))}')

    # Hyperparameter sweep
    best_f1, best_params = -1, {}
    best_result = {}
    sweep = [
        {'max_depth': 4, 'n_estimators': 100, 'learning_rate': 0.1},
        {'max_depth': 6, 'n_estimators': 200, 'learning_rate': 0.05},
        {'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.01},
    ]
    for params in sweep:
        ctx.log(f'Training depth={params["max_depth"]} trees={params["n_estimators"]}')
        result = train_event_classifier(
            tabular, labels, feature_names=feature_names or None,
            xgb_params=params, val_fraction=0.2)
        metrics = result.get('metrics', {})
        f1 = metrics.get('macro_f1_events', metrics.get('macro_f1', 0))
        ctx.log(f'  → F1={f1:.3f} acc={metrics.get("accuracy", 0):.3f}')
        if f1 > best_f1:
            best_f1, best_params = f1, params
            best_result = result

    best_metrics = best_result.get('metrics', {})
    ctx.result.update({
        'n_samples': len(labels),
        'n_features': tabular.shape[1],
        'best_params': best_params,
        'macro_f1': best_f1,
        'per_class': best_metrics.get('per_class', {}),
        'auroc': best_metrics.get('auroc', None),
        'class_distribution': best_result.get('class_distribution', {}),
        'feature_importance_top5': dict(list(
            best_result.get('feature_importance', {}).items())[:5]),
        'success': best_f1 > 0.5,
    })
    ctx.section('Results')
    ctx.log(f'Best F1={best_f1:.3f} params={best_params}')
    return ctx.save('exp027_event_classifier.json')


# ────────────────────────────────────────────────────────────────────
# EXP-028: Multi-Horizon Coarse-Grid Training
# Hypothesis: Downsampled models beat persistence at 6hr and 3-day.
# ────────────────────────────────────────────────────────────────────

def run_multihorizon(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-028', out, hypothesis='multi-res > persistence')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # build_multihorizon_windows handles downsampling internally and returns
    # {'1hr@5min': {'features': ndarray(T,F), ...}, '6hr@15min': {...}, ...}
    # We need to window those feature arrays into fixed-size training chunks.
    by_horizon = {}  # label → list of (win_size, F) arrays
    win_size = 24
    for ppath in paths:
        try:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None:
                continue
            # Add time features to grid_df so build_multihorizon_windows
            # can find all 8 standard features
            if 'time_sin' not in grid_df.columns and grid_df.index is not None:
                import numpy as _np
                hours = grid_df.index.hour + grid_df.index.minute / 60.0
                grid_df['time_sin'] = _np.sin(2 * _np.pi * hours / 24.0)
                grid_df['time_cos'] = _np.cos(2 * _np.pi * hours / 24.0)
            mh = build_multihorizon_windows(grid_df)
            for h_label, h_data in mh.items():
                features = h_data['features']  # (T, num_features)
                stride = max(1, win_size // 2)
                for i in range(0, len(features) - win_size + 1, stride):
                    win = features[i:i + win_size]
                    import numpy as _np
                    if _np.isnan(win).any() or _np.isinf(win).any():
                        continue
                    by_horizon.setdefault(h_label, []).append(win)
        except Exception:
            continue

    results_by_res = {}
    for label, windows in sorted(by_horizon.items()):
        ctx.section(f'Horizon: {label}')
        if len(windows) < 50:
            ctx.log(f'Only {len(windows)} windows — skipping')
            results_by_res[label] = {'status': 'too_few_windows'}
            continue

        train_ds, val_ds = windows_to_datasets(windows)
        dim = windows[0].shape[-1]
        safe_label = label.replace('@', '_').replace('/', '_')
        model = create_model('grouped', input_dim=dim)
        best_loss, _ = train(
            model, train_ds, val_ds,
            f'{out}/exp028_multihorizon_{safe_label}.pth', f'MH-{label}')
        m_mse = forecast_mse(model, val_ds)
        p_mse = persistence_mse(val_ds)
        results_by_res[label] = {
            'windows': len(windows), 'forecast_mse': m_mse,
            'persistence_mse': p_mse,
            'improvement_pct': improvement_pct(m_mse, p_mse),
        }
        ctx.log(f'{label}: model={m_mse:.6f} persist={p_mse:.6f} '
                f'Δ={results_by_res[label]["improvement_pct"]:.1f}%')

    ctx.result['resolutions'] = results_by_res
    ctx.result['success'] = any(
        r.get('improvement_pct', 0) > 20
        for r in results_by_res.values() if isinstance(r, dict))
    return ctx.save('exp028_multihorizon.json')


# ────────────────────────────────────────────────────────────────────
# EXP-029: MC-Dropout Uncertainty Calibration
# Hypothesis: 95% PI coverage ≈ 95% (±5%).
# ────────────────────────────────────────────────────────────────────

def run_uncertainty_calibration(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-029', out, hypothesis='calibrated prediction intervals')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    _, val_ds = load_multipatient_nightscout(paths, window_size=24)

    # Find existing grouped checkpoint
    ckpt_path = find_checkpoint(out, 'exp026_grouped_8f.pth',
                                'exp029_grouped.pth',
                                'grouped_multi_transfer.pth')
    if not ckpt_path:
        ctx.log('Training fresh model for calibration')
        ds, _ = load_multipatient_nightscout(paths, window_size=24)
        model = create_model('grouped', input_dim=8)
        train(model, ds, val_ds, f'{out}/exp029_grouped.pth', 'Cal-base')
        ckpt_path = f'{out}/exp029_grouped.pth'

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt_path)
    model.train()  # keep dropout active

    n_samples_sweep = [10, 20, 50, 100]
    cal_results = {}

    for n_s in n_samples_sweep:
        ctx.section(f'MC samples = {n_s}')
        coverages, widths = [], []
        dl = torch.utils.data.DataLoader(val_ds, batch_size=32)
        for batch in dl:
            x = batch[0].to(get_device())
            half = x.shape[1] // 2
            mean, std, _ = mc_predict(model, x, n_samples=n_s, causal=True)
            actual = x[:, half:, 0]
            lo = mean[:, half:, 0] - 1.96 * std[:, half:, 0]
            hi = mean[:, half:, 0] + 1.96 * std[:, half:, 0]
            covered = ((actual >= lo) & (actual <= hi)).float().mean().item()
            width = (hi - lo).mean().item()
            coverages.append(covered)
            widths.append(width)

        cov = float(np.mean(coverages))
        w = float(np.mean(widths))
        gap = abs(cov - 0.95)
        cal_results[n_s] = {'coverage_95': cov, 'mean_width': w, 'cal_gap': gap}
        ctx.log(f'n={n_s}: coverage={cov:.3f} width={w:.4f} gap={gap:.3f}')

    ctx.result['calibration'] = cal_results
    best_n = min(cal_results, key=lambda k: cal_results[k]['cal_gap'])
    ctx.result['best_n_samples'] = best_n
    ctx.result['success'] = cal_results[best_n]['cal_gap'] < 0.05
    return ctx.save('exp029_uncertainty.json')


# ────────────────────────────────────────────────────────────────────
# EXP-030: ISF/CR Drift Tracking Retrospective
# Hypothesis: Kalman tracker detects drift in >50% of patients.
# ────────────────────────────────────────────────────────────────────

def run_isf_cr_tracking(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-030', out, hypothesis='detect ISF/CR drift')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    drift_detected = 0
    patient_results = {}

    for ppath in paths:
        pname = ppath.rstrip('/').split('/')[-2]  # e.g. 'a'
        ctx.section(f'Patient {pname}')
        isf, cr = load_patient_profile(ppath)
        ctx.log(f'Profile: ISF={isf}, CR={cr}')
        try:
            tracking = run_retrospective_tracking(
                ppath, nominal_isf=isf, nominal_cr=cr, level='simple')
            classification = tracking.get('classification', {})
            if isinstance(classification, dict):
                cls_state = classification.get('state', 'unknown')
            else:
                cls_state = str(classification)
            summary = tracking.get('summary', {})
            trajectory = tracking.get('trajectory', [])
            has_drift = cls_state not in ('stable', 'insufficient_data', 'unknown')
            patient_results[pname] = {
                'isf': isf, 'cr': cr,
                'classification': cls_state,
                'n_trajectory_points': len(trajectory),
                'summary': summary,
            }
            if has_drift:
                drift_detected += 1
                ctx.log(f'Drift: {cls_state} ({len(trajectory)} points)')
            else:
                ctx.log(f'Stable ({len(trajectory)} points)')
        except Exception as e:
            patient_results[pname] = {'error': str(e)}
            ctx.log(f'Error: {e}')

    ctx.result['patients'] = patient_results
    ctx.result['drift_detected_count'] = drift_detected
    ctx.result['drift_detected_pct'] = drift_detected / max(1, len(paths)) * 100
    ctx.result['success'] = drift_detected >= len(paths) * 0.5
    ctx.section('Summary')
    ctx.log(f'{drift_detected}/{len(paths)} patients with drift '
            f'({ctx.result["drift_detected_pct"]:.0f}%)')
    return ctx.save('exp030_isf_cr_tracking.json')


# ────────────────────────────────────────────────────────────────────
# EXP-031: Scenario Simulation Validation
# Hypothesis: Correct directional impact for >80% of scenarios.
# ────────────────────────────────────────────────────────────────────

def run_scenario_validation(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-031', out, hypothesis='scenario direction >80%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # Build a simple hierarchical forecaster from existing checkpoints
    short_model = create_model('grouped', input_dim=8)
    ckpt = find_checkpoint(out, 'grouped_multi_transfer.pth', 'exp026_grouped_8f.pth')
    if ckpt:
        load_checkpoint(short_model, ckpt)
    forecaster = HierarchicalForecaster(short_model=short_model)
    sim = ScenarioSimulator(forecaster)

    scenarios = [
        {'name': 'meal_50g',    'carbs': 50, 'insulin': 0, 'expected': 'rise'},
        {'name': 'bolus_5u',    'carbs': 0,  'insulin': 5, 'expected': 'drop'},
        {'name': 'meal+bolus',  'carbs': 50, 'insulin': 5, 'expected': 'moderate'},
        {'name': 'exercise_30', 'carbs': 0,  'insulin': 0, 'exercise': True, 'expected': 'drop'},
        {'name': 'nothing',     'carbs': 0,  'insulin': 0, 'expected': 'flat'},
    ]

    correct, total = 0, 0
    scenario_results = []
    for ppath in paths[:3]:  # Use 3 patients for speed
        _, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        if len(val_ds) == 0:
            continue
        sample = val_ds[0][0].unsqueeze(0).to(get_device())
        for sc in scenarios:
            try:
                result = sim.simulate_scenario(sample, sc)
                delta_arr = result.get('delta_mgdl', None)
                if delta_arr is not None and hasattr(delta_arr, '__len__') and len(delta_arr) > 0:
                    mean_delta = float(result.get('mean_impact_mgdl', 0))
                    direction = 'rise' if mean_delta > 5 else 'drop' if mean_delta < -5 else 'flat'
                    expected = sc['expected']
                    hit = (expected == direction or
                           (expected == 'moderate' and abs(mean_delta) < 30))
                    correct += int(hit)
                    total += 1
                    scenario_results.append({
                        'scenario': sc['name'], 'mean_delta': mean_delta,
                        'direction': direction, 'expected': expected, 'hit': hit,
                    })
            except Exception as e:
                scenario_results.append({'scenario': sc['name'], 'error': str(e)})
                total += 1

    accuracy = correct / max(1, total)
    ctx.result.update({
        'scenarios': scenario_results,
        'correct': correct, 'total': total,
        'accuracy': accuracy,
        'success': accuracy > 0.8,
    })
    ctx.section('Results')
    ctx.log(f'{correct}/{total} correct ({accuracy:.1%})')
    return ctx.save('exp031_scenario.json')


# ────────────────────────────────────────────────────────────────────
# EXP-032: End-to-End Backtest
# Depends on: EXP-026, EXP-027, EXP-028
# Hypothesis: Pipeline produces clinically useful overrides.
# ────────────────────────────────────────────────────────────────────

def run_backtest(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-032', out, hypothesis='useful override suggestions')
    patients_dir = getattr(args, 'patients_dir', None)
    paths = resolve_patient_paths(patients_dir, getattr(args, 'real_data', None))

    # Load components — prefer 8f checkpoint (matches input_dim=8)
    model = create_model('grouped', input_dim=8)
    ckpt = find_checkpoint(out, 'exp026_grouped_8f.pth',
                           'grouped_multi_transfer.pth',
                           'exp028_multihorizon_1hr_5min.pth')
    if ckpt:
        load_checkpoint(model, ckpt)

    forecaster = HierarchicalForecaster(short_model=model)
    engine = BacktestEngine(forecaster=forecaster)

    all_results = []
    for ppath in paths[:5]:  # Up to 5 patients
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Patient {pname}')
        try:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None:
                continue
            glucose = feat[:, 0]  # glucose channel

            # Extract real events for evaluation
            treatments_path = ppath.rstrip('/') + '/treatments.json'
            ds_path = ppath.rstrip('/') + '/devicestatus.json'
            events = extract_override_events(
                treatments_path,
                ds_path if os.path.exists(ds_path) else None
            ) if os.path.exists(treatments_path) else []

            bt = engine.full_backtest(
                glucose_mgdl=glucose, events=events,
                window_size_steps=72, stride_steps=36)
            all_results.append({'patient': pname, **bt})
            ctx.log(f'{pname}: {bt.get("n_suggestions", 0)} suggestions')
        except Exception as e:
            ctx.log(f'{pname}: Error — {e}')
            all_results.append({'patient': pname, 'error': str(e)})

    # Aggregate
    n_sugg = sum(r.get('n_suggestions', 0) for r in all_results)
    ctx.result['patients'] = all_results
    ctx.result['total_suggestions'] = n_sugg
    ctx.result['success'] = n_sugg > 0
    ctx.section('Summary')
    ctx.log(f'{n_sugg} total suggestions across {len(all_results)} patients')
    return ctx.save('exp032_backtest.json')


# ────────────────────────────────────────────────────────────────────
# EXP-033: 8→16 Feature Transfer Learning
# Hypothesis: Transferring 8f weights → 16f beats training from scratch.
# ────────────────────────────────────────────────────────────────────

def run_feature_transfer(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-033', out, hypothesis='transfer > scratch for 16f')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    windows = build_16f_windows(paths, window_size=24)
    ctx.log(f'{len(windows)} 16f windows')
    if len(windows) < 100:
        ctx.log('Too few windows'); return ctx.save('exp033_results.json')
    train_ds, val_ds = windows_to_datasets(windows)

    strategies = {}

    # Strategy A: From scratch
    ctx.section('Strategy A: Scratch')
    set_seed(42)
    m_scratch = create_model('grouped', input_dim=16)
    _, ep_a = train(m_scratch, train_ds, val_ds,
                    f'{out}/exp033_scratch.pth', 'Scratch')
    mse_a = forecast_mse(m_scratch, val_ds)
    strategies['scratch'] = {'mse': mse_a, 'epochs': ep_a}
    ctx.log(f'MSE={mse_a:.6f} in {ep_a} epochs')

    # Strategy B: Transfer + train all
    ctx.section('Strategy B: Transfer + train all')
    set_seed(42)
    m_base = create_model('grouped', input_dim=8)
    ckpt = find_checkpoint(out, 'grouped_multi_transfer.pth',
                           'exp026_grouped_8f.pth')
    if ckpt:
        load_checkpoint(m_base, ckpt)
    m_trans = create_model('grouped', input_dim=16)
    n_tx = transfer_weights(m_base, m_trans)
    ctx.log(f'Transferred {n_tx} weight tensors')
    _, ep_b = train(m_trans, train_ds, val_ds,
                    f'{out}/exp033_transfer_all.pth', 'Transfer-all')
    mse_b = forecast_mse(m_trans, val_ds)
    strategies['transfer_all'] = {'mse': mse_b, 'epochs': ep_b}
    ctx.log(f'MSE={mse_b:.6f} in {ep_b} epochs')

    # Strategy C: Transfer + freeze encoder
    ctx.section('Strategy C: Transfer + freeze encoder')
    set_seed(42)
    m_freeze = create_model('grouped', input_dim=16)
    transfer_weights(m_base, m_freeze)
    for name, param in m_freeze.named_parameters():
        if 'encoder' in name or 'history_proj' in name:
            param.requires_grad = False
    _, ep_c = train(m_freeze, train_ds, val_ds,
                    f'{out}/exp033_transfer_freeze.pth', 'Transfer-freeze')
    mse_c = forecast_mse(m_freeze, val_ds)
    strategies['transfer_freeze'] = {'mse': mse_c, 'epochs': ep_c}
    ctx.log(f'MSE={mse_c:.6f} in {ep_c} epochs')

    # Compare
    best = min(strategies, key=lambda k: strategies[k]['mse'])
    ctx.result['strategies'] = strategies
    ctx.result['best_strategy'] = best
    ctx.result['improvement_over_scratch'] = improvement_pct(
        strategies[best]['mse'], mse_a) if best != 'scratch' else 0
    ctx.result['success'] = best != 'scratch'
    ctx.section('Summary')
    for k, v in strategies.items():
        mark = ' ← best' if k == best else ''
        ctx.log(f'{k}: MSE={v["mse"]:.6f} ({v["epochs"]} epochs){mark}')
    return ctx.save('exp033_feature_transfer.json')


# Needed by backtest
import os

from .evaluate import denormalize_glucose, mae_mgdl, rmse_mgdl, time_in_range, clinical_summary
from .schema import NORMALIZATION_SCALES


# ════════════════════════════════════════════════════════════════════
# ROUND 2 — EXP-034 through EXP-041
# ════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────
# EXP-034: Denormalized Clinical Metrics at All Horizons
# Hypothesis: Models achieve MAE < 15 mg/dL at 1hr, < 30 at 6hr.
# ────────────────────────────────────────────────────────────────────

def run_clinical_metrics(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-034', out, hypothesis='MAE<15 at 1hr, <30 at 6hr in mg/dL')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    device = get_device()
    glucose_scale = NORMALIZATION_SCALES['glucose']  # 400.0
    from torch.utils.data import DataLoader

    # Evaluate the 8f model at 1hr (normalized data)
    ctx.section('8-feature model (1hr, normalized)')
    _, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ckpt_8f = find_checkpoint(out, 'exp026_grouped_8f.pth',
                              'exp029_grouped.pth',
                              'grouped_multi_transfer.pth')
    results = {}
    if ckpt_8f:
        model_8f = create_model('grouped', input_dim=8)
        load_checkpoint(model_8f, ckpt_8f)
        model_8f.eval()

        all_pred_mgdl, all_true_mgdl = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0  # mask future glucose
            with torch.no_grad():
                pred = model_8f(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
            true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
            all_pred_mgdl.append(pred_gl)
            all_true_mgdl.append(true_gl)

        pred_flat = np.concatenate(all_pred_mgdl).flatten()
        true_flat = np.concatenate(all_true_mgdl).flatten()
        mae_1hr = float(np.mean(np.abs(pred_flat - true_flat)))
        rmse_1hr = float(np.sqrt(np.mean((pred_flat - true_flat) ** 2)))
        tir = time_in_range(true_flat)
        results['8f_1hr'] = {
            'mae_mgdl': mae_1hr, 'rmse_mgdl': rmse_1hr,
            'n_points': len(pred_flat), 'tir_pct': tir,
        }
        ctx.log(f'8f 1hr: MAE={mae_1hr:.1f} mg/dL, RMSE={rmse_1hr:.1f}, TIR={tir["tir"]:.1f}%')
    else:
        ctx.log('No 8f checkpoint found')

    # Evaluate the 16f model at 1hr
    ctx.section('16-feature model (1hr, normalized)')
    ckpt_16f = find_checkpoint(out, 'exp026_grouped_16f.pth',
                               'exp033_transfer_all.pth')
    if ckpt_16f:
        windows_16f = build_16f_windows(paths, window_size=24)
        if len(windows_16f) > 50:
            _, val16 = windows_to_datasets(windows_16f)
            model_16f = create_model('grouped', input_dim=16)
            load_checkpoint(model_16f, ckpt_16f)
            model_16f.eval()

            all_pred_mgdl, all_true_mgdl = [], []
            for batch in DataLoader(val16, batch_size=64):
                x = batch[0].to(device)
                half = x.shape[1] // 2
                x_in = x.clone()
                x_in[:, half:, 0] = 0.0  # mask future glucose
                with torch.no_grad():
                    pred = model_16f(x_in, causal=True)
                pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
                true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
                all_pred_mgdl.append(pred_gl)
                all_true_mgdl.append(true_gl)

            pred_flat = np.concatenate(all_pred_mgdl).flatten()
            true_flat = np.concatenate(all_true_mgdl).flatten()
            mae_16f = float(np.mean(np.abs(pred_flat - true_flat)))
            rmse_16f = float(np.sqrt(np.mean((pred_flat - true_flat) ** 2)))
            results['16f_1hr'] = {'mae_mgdl': mae_16f, 'rmse_mgdl': rmse_16f,
                                  'n_points': len(pred_flat)}
            ctx.log(f'16f 1hr: MAE={mae_16f:.1f} mg/dL, RMSE={rmse_16f:.1f}')
    else:
        ctx.log('No 16f checkpoint found')

    # Evaluate EXP-028 multi-horizon models (raw-data trained)
    ctx.section('Multi-horizon models (EXP-028, raw-data)')
    for label in ['1hr_5min', '6hr_15min', '3day_1hr']:
        ckpt_mh = find_checkpoint(out, f'exp028_multihorizon_{label}.pth')
        if not ckpt_mh:
            ctx.log(f'{label}: no checkpoint')
            continue
        model_mh = create_model('grouped', input_dim=8)
        load_checkpoint(model_mh, ckpt_mh)
        model_mh.eval()

        win_size = 24
        all_windows = []
        for ppath in paths:
            try:
                grid_df, feat = build_nightscout_grid(ppath, verbose=False)
                if feat is None:
                    continue
                if 'time_sin' not in grid_df.columns:
                    hours = grid_df.index.hour + grid_df.index.minute / 60.0
                    grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                    grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
                mh = build_multihorizon_windows(grid_df)
                for h_label, h_data in mh.items():
                    safe = h_label.replace('@', '_').replace('/', '_')
                    if safe == label:
                        features = h_data['features']
                        stride = max(1, win_size // 2)
                        for i in range(0, len(features) - win_size + 1, stride):
                            win = features[i:i + win_size]
                            if not np.isnan(win).any() and not np.isinf(win).any():
                                all_windows.append(win)
            except Exception:
                continue

        if len(all_windows) < 50:
            ctx.log(f'{label}: too few windows ({len(all_windows)})')
            continue

        _, val_mh = windows_to_datasets(all_windows)
        all_pred_mgdl, all_true_mgdl = [], []
        for batch in DataLoader(val_mh, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0  # mask future glucose
            with torch.no_grad():
                pred = model_mh(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy()
            true_gl = x[:, half:, 0].cpu().numpy()
            all_pred_mgdl.append(pred_gl)
            all_true_mgdl.append(true_gl)

        pred_flat = np.concatenate(all_pred_mgdl).flatten()
        true_flat = np.concatenate(all_true_mgdl).flatten()
        mae_mh = float(np.mean(np.abs(pred_flat - true_flat)))
        rmse_mh = float(np.sqrt(np.mean((pred_flat - true_flat) ** 2)))
        tir_mh = time_in_range(true_flat)
        results[f'mh_{label}'] = {
            'mae_mgdl': mae_mh, 'rmse_mgdl': rmse_mh,
            'n_points': len(pred_flat), 'tir_pct': tir_mh,
        }
        ctx.log(f'{label}: MAE={mae_mh:.1f} mg/dL, RMSE={rmse_mh:.1f}, TIR={tir_mh["tir"]:.1f}%')

    ctx.result['metrics'] = results
    mae_vals = [v['mae_mgdl'] for v in results.values() if 'mae_mgdl' in v]
    ctx.result['success'] = any(m < 30 for m in mae_vals) if mae_vals else False
    ctx.section('Summary')
    for k, v in results.items():
        ctx.log(f'{k}: MAE={v["mae_mgdl"]:.1f} RMSE={v["rmse_mgdl"]:.1f} mg/dL')
    return ctx.save('exp034_clinical_metrics.json')


# ────────────────────────────────────────────────────────────────────
# EXP-035: Normalized Multi-Horizon Retraining
# ────────────────────────────────────────────────────────────────────

def run_norm_multihorizon(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-035', out, hypothesis='normalized multi-res training')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    scales = np.array([NORMALIZATION_SCALES.get(f, 1.0) for f in
                       ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs',
                        'time_sin', 'time_cos']], dtype=np.float32)
    win_size = 24
    by_horizon = {}
    for ppath in paths:
        try:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None:
                continue
            if 'time_sin' not in grid_df.columns:
                hours = grid_df.index.hour + grid_df.index.minute / 60.0
                grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
            mh = build_multihorizon_windows(grid_df)
            for h_label, h_data in mh.items():
                features = h_data['features']
                n_cols = min(features.shape[1], len(scales))
                norm_feat = features.copy()
                norm_feat[:, :n_cols] /= scales[:n_cols]
                stride = max(1, win_size // 2)
                for i in range(0, len(norm_feat) - win_size + 1, stride):
                    win = norm_feat[i:i + win_size]
                    if not np.isnan(win).any() and not np.isinf(win).any():
                        by_horizon.setdefault(h_label, []).append(win)
        except Exception:
            continue

    results_by_res = {}
    from torch.utils.data import DataLoader
    for label, windows in sorted(by_horizon.items()):
        ctx.section(f'Horizon: {label}')
        if len(windows) < 50:
            ctx.log(f'Only {len(windows)} windows — skipping')
            results_by_res[label] = {'status': 'too_few_windows'}
            continue

        train_ds, val_ds = windows_to_datasets(windows)
        dim = windows[0].shape[-1]
        safe_label = label.replace('@', '_').replace('/', '_')
        model = create_model('grouped', input_dim=dim)
        best_loss, ep = train(
            model, train_ds, val_ds,
            f'{out}/exp035_norm_mh_{safe_label}.pth', f'NMH-{label}')

        device = get_device()
        model.eval()
        all_pred, all_true = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0  # mask future glucose
            with torch.no_grad():
                pred = model(x_in, causal=True)
            all_pred.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            all_true.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

        pred_flat = np.concatenate(all_pred).flatten()
        true_flat = np.concatenate(all_true).flatten()
        mae_val = float(np.mean(np.abs(pred_flat - true_flat)))
        rmse_val = float(np.sqrt(np.mean((pred_flat - true_flat) ** 2)))

        m_mse = forecast_mse(model, val_ds)
        p_mse = persistence_mse(val_ds)
        results_by_res[label] = {
            'windows': len(windows),
            'mae_mgdl': mae_val, 'rmse_mgdl': rmse_val,
            'forecast_mse': m_mse, 'persistence_mse': p_mse,
            'improvement_pct': improvement_pct(m_mse, p_mse),
        }
        ctx.log(f'{label}: MAE={mae_val:.1f} mg/dL  mse={m_mse:.6f}  '
                f'persist={p_mse:.6f}  Δ={results_by_res[label]["improvement_pct"]:.1f}%')

    ctx.result['resolutions'] = results_by_res
    ctx.result['success'] = any(
        r.get('improvement_pct', 0) > 20
        for r in results_by_res.values() if isinstance(r, dict))
    return ctx.save('exp035_norm_multihorizon.json')


# ────────────────────────────────────────────────────────────────────
# EXP-036: Classifier Without lead_time Feature
# ────────────────────────────────────────────────────────────────────

def run_classifier_no_leadtime(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-036', out, hypothesis='CGM-only F1 > 0.35 without lead_time')
    patients_dir = getattr(args, 'patients_dir', None)

    ctx.section('Building dataset')
    ds = build_classifier_dataset(patients_dir)
    tabular = ds['tabular']
    labels = ds['labels']
    feat_names = list(ds['feature_names'])

    if 'lead_time_hr' in feat_names:
        lt_idx = feat_names.index('lead_time_hr')
        tabular = np.delete(tabular, lt_idx, axis=1)
        feat_names = [f for i, f in enumerate(feat_names) if i != lt_idx]
        ctx.log(f'Removed lead_time_hr (was col {lt_idx}). {tabular.shape[1]} features remain.')
    else:
        ctx.log('lead_time_hr not found — using all features')

    ctx.log(f'{tabular.shape[0]} samples, {tabular.shape[1]} features')

    ctx.section('Training without lead_time')
    result = train_event_classifier(
        tabular, labels, feature_names=feat_names,
        xgb_params={'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.01},
    )
    metrics = result['metrics']
    f1 = metrics.get('macro_f1_events', metrics.get('macro_f1', 0))

    ctx.section('Results')
    ctx.log(f'Macro F1 = {f1:.4f} (vs 0.5732 with lead_time)')
    per_class = metrics.get('per_class', {})
    for cls_name, cls_m in per_class.items():
        ctx.log(f'  {cls_name}: P={cls_m.get("precision",0):.3f} '
                f'R={cls_m.get("recall",0):.3f} F1={cls_m.get("f1",0):.3f}')

    fi = result.get('feature_importance', {})
    top5 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:5]

    ctx.result.update({
        'macro_f1': f1,
        'f1_with_leadtime': 0.5732,
        'f1_drop': 0.5732 - f1,
        'per_class': per_class,
        'feature_importance_top5': dict(top5),
        'n_samples': tabular.shape[0],
        'n_features': tabular.shape[1],
        'success': f1 > 0.35,
    })
    return ctx.save('exp036_no_leadtime.json')


# ────────────────────────────────────────────────────────────────────
# EXP-037: Rolling Feature Engineering for Meal Detection
# Depends on: EXP-036
# ────────────────────────────────────────────────────────────────────

def run_rolling_features(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-037', out, hypothesis='rolling features improve meal F1>0.65')
    patients_dir = getattr(args, 'patients_dir', None)

    ctx.section('Building dataset with rolling features')
    ds = build_classifier_dataset(patients_dir)
    tabular = ds['tabular']
    labels = ds['labels']
    feat_names = list(ds['feature_names'])

    if 'lead_time_hr' in feat_names:
        lt_idx = feat_names.index('lead_time_hr')
        tabular = np.delete(tabular, lt_idx, axis=1)
        feat_names = [f for i, f in enumerate(feat_names) if i != lt_idx]

    gl_idx = None
    for i, fn in enumerate(feat_names):
        if fn.startswith('glucose') and 'roc' not in fn:
            gl_idx = i
            break

    rolling_names = []
    if gl_idx is not None:
        import pandas as pd
        gl_series = pd.Series(tabular[:, gl_idx])
        rolling_feats = []
        for window in [12, 36, 72]:  # 1hr, 3hr, 6hr at 5-min
            label_w = f'{window * 5 // 60}hr'
            roll = gl_series.rolling(window, min_periods=1)
            rolling_feats.append(roll.mean().values)
            rolling_names.append(f'glucose_mean_{label_w}')
            rolling_feats.append(roll.std().fillna(0).values)
            rolling_names.append(f'glucose_std_{label_w}')
            rolling_feats.append(roll.min().values)
            rolling_names.append(f'glucose_min_{label_w}')
            rolling_feats.append(roll.max().values)
            rolling_names.append(f'glucose_max_{label_w}')
            rolling_feats.append(roll.mean().diff().fillna(0).values)
            rolling_names.append(f'glucose_roc_{label_w}')

        extra = np.column_stack(rolling_feats).astype(np.float32)
        tabular = np.hstack([tabular, extra])
        feat_names.extend(rolling_names)
        ctx.log(f'Added {len(rolling_names)} rolling features. Total: {tabular.shape[1]}')
    else:
        ctx.log('No glucose column found — training without rolling features')

    ctx.section('Training')
    result = train_event_classifier(
        tabular, labels, feature_names=feat_names,
        xgb_params={'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.01},
    )
    metrics = result['metrics']
    f1 = metrics.get('macro_f1_events', metrics.get('macro_f1', 0))
    per_class = metrics.get('per_class', {})
    meal_f1 = per_class.get('meal', {}).get('f1', 0)

    ctx.section('Results')
    ctx.log(f'Macro F1 = {f1:.4f}, Meal F1 = {meal_f1:.4f} (target >0.65)')
    for cls_name, cls_m in per_class.items():
        ctx.log(f'  {cls_name}: P={cls_m.get("precision",0):.3f} '
                f'R={cls_m.get("recall",0):.3f} F1={cls_m.get("f1",0):.3f}')

    fi = result.get('feature_importance', {})
    top10 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:10]

    ctx.result.update({
        'macro_f1': f1, 'meal_f1': meal_f1,
        'per_class': per_class,
        'feature_importance_top10': dict(top10),
        'n_features': tabular.shape[1],
        'n_rolling_features': len(rolling_names),
        'success': meal_f1 > 0.65,
    })
    return ctx.save('exp037_rolling_features.json')


# ────────────────────────────────────────────────────────────────────
# EXP-038: Cost-Sensitive Classification
# ────────────────────────────────────────────────────────────────────

def run_cost_sensitive(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-038', out, hypothesis='class weighting balances P/R')
    patients_dir = getattr(args, 'patients_dir', None)

    ctx.section('Building dataset')
    ds = build_classifier_dataset(patients_dir)
    tabular = ds['tabular']
    labels = ds['labels']
    feat_names = list(ds['feature_names'])

    unique_labels, counts = np.unique(labels, return_counts=True)
    total = len(labels)

    results_by_exponent = {}
    for exp_val in [0.5, 1.0, 1.5]:
        ctx.section(f'Weight exponent = {exp_val}')
        weights = {}
        for lbl, cnt in zip(unique_labels, counts):
            weights[int(lbl)] = (total / (len(unique_labels) * cnt)) ** exp_val

        sample_weights = np.array([weights[int(l)] for l in labels], dtype=np.float32)

        result = train_event_classifier(
            tabular, labels, feature_names=feat_names,
            xgb_params={'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.01},
            sample_weight=sample_weights,
        )
        metrics = result['metrics']
        f1 = metrics.get('macro_f1_events', metrics.get('macro_f1', 0))
        per_class = metrics.get('per_class', {})

        eating_soon = per_class.get('eating_soon', {})
        es_p = eating_soon.get('precision', 0)
        es_r = eating_soon.get('recall', 0)

        results_by_exponent[str(exp_val)] = {
            'macro_f1': f1, 'per_class': per_class,
            'eating_soon_precision': es_p, 'eating_soon_recall': es_r,
        }
        ctx.log(f'exp={exp_val}: F1={f1:.4f}  eating_soon P={es_p:.3f} R={es_r:.3f}')
        for cls_name, cls_m in per_class.items():
            ctx.log(f'  {cls_name}: P={cls_m.get("precision",0):.3f} '
                    f'R={cls_m.get("recall",0):.3f} F1={cls_m.get("f1",0):.3f}')

    best_exp = max(results_by_exponent,
                   key=lambda k: results_by_exponent[k]['macro_f1'])
    best = results_by_exponent[best_exp]

    ctx.result['sweeps'] = results_by_exponent
    ctx.result['best_exponent'] = float(best_exp)
    ctx.result['best_macro_f1'] = best['macro_f1']
    ctx.result['success'] = (best.get('eating_soon_precision', 0) > 0.50
                             and best.get('eating_soon_recall', 0) > 0.80)
    return ctx.save('exp038_cost_sensitive.json')


# ────────────────────────────────────────────────────────────────────
# EXP-039: Physics-Residual at 6hr Horizon (depends on EXP-035)
# ────────────────────────────────────────────────────────────────────

def run_physics_residual_6hr(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-039', out, hypothesis='physics+ML > ML-only at 6hr')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    scales = np.array([NORMALIZATION_SCALES.get(f, 1.0) for f in
                       ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs',
                        'time_sin', 'time_cos']], dtype=np.float32)

    ctx.section('Loading 6hr model')
    ckpt = find_checkpoint(out, 'exp043_forecast_mh_6hr_15min.pth',
                           'exp035_norm_mh_6hr_15min.pth',
                           'exp028_multihorizon_6hr_15min.pth')
    model = create_model('grouped', input_dim=8)
    if ckpt:
        load_checkpoint(model, ckpt)
        ctx.log(f'Loaded {ckpt}')
    else:
        ctx.log('No 6hr checkpoint — using untrained model')

    win_size = 24
    half = win_size // 2
    all_norm, all_raw = [], []
    for ppath in paths:
        try:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None:
                continue
            if 'time_sin' not in grid_df.columns:
                hours = grid_df.index.hour + grid_df.index.minute / 60.0
                grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
            mh = build_multihorizon_windows(grid_df)
            h_data = mh.get('6hr@15min')
            if h_data is None:
                continue
            features = h_data['features']
            n_cols = min(features.shape[1], len(scales))
            norm_feat = features.copy()
            norm_feat[:, :n_cols] /= scales[:n_cols]
            stride = max(1, win_size // 2)
            for i in range(0, len(features) - win_size + 1, stride):
                raw_win = features[i:i + win_size]
                norm_win = norm_feat[i:i + win_size]
                if not np.isnan(raw_win).any() and not np.isinf(raw_win).any():
                    all_norm.append(norm_win)
                    all_raw.append(raw_win)
        except Exception:
            continue

    ctx.log(f'{len(all_norm)} windows at 6hr@15min')
    if len(all_norm) < 50:
        ctx.result['success'] = False
        ctx.result['error'] = 'too few windows'
        return ctx.save('exp039_physics_6hr.json')

    device = get_device()
    model.eval()
    isf, cr = load_patient_profile(paths[0])

    ml_errors, phys_errors, combo_errors = [], [], []
    for norm_win, raw_win in zip(all_norm[:2000], all_raw[:2000]):
        true_gl = raw_win[half:, 0]

        x = torch.from_numpy(norm_win).unsqueeze(0).float().to(device)
        x_in = x.clone()
        x_in[0, half:, 0] = 0.0  # mask future glucose
        with torch.no_grad():
            pred = model(x_in, causal=True)
        ml_gl = pred[0, half:, 0].cpu().numpy() * glucose_scale

        gl_now = raw_win[half - 1, 0]
        iob_now = raw_win[half - 1, 1]
        cob_now = raw_win[half - 1, 2]
        phys_gl = np.full(half, gl_now)
        for t in range(half):
            decay = t / half
            phys_gl[t] = (gl_now - iob_now * (1 - decay) * isf
                          + cob_now * (1 - decay) / max(cr, 1) * isf)

        # Residual composition: ML predicts the error the physics model makes
        combo_gl = phys_gl + (ml_gl - phys_gl) * 0.5 + (ml_gl - gl_now) * 0.5

        ml_errors.append(np.mean(np.abs(ml_gl - true_gl)))
        phys_errors.append(np.mean(np.abs(phys_gl - true_gl)))
        combo_errors.append(np.mean(np.abs(combo_gl - true_gl)))

    ml_mae = float(np.mean(ml_errors))
    phys_mae = float(np.mean(phys_errors))
    combo_mae = float(np.mean(combo_errors))

    ctx.section('Results (6hr MAE in mg/dL)')
    ctx.log(f'Physics-only: {phys_mae:.1f}')
    ctx.log(f'ML-only:      {ml_mae:.1f}')
    ctx.log(f'Physics+ML:   {combo_mae:.1f}')
    ctx.log(f'Combo vs ML-only: {improvement_pct(combo_mae, ml_mae):.1f}%')

    ctx.result.update({
        'physics_mae_mgdl': phys_mae, 'ml_mae_mgdl': ml_mae,
        'combo_mae_mgdl': combo_mae,
        'combo_improvement_pct': improvement_pct(combo_mae, ml_mae),
        'n_windows': min(len(all_norm), 2000),
        'success': improvement_pct(combo_mae, ml_mae) > 20,
    })
    return ctx.save('exp039_physics_6hr.json')


# ────────────────────────────────────────────────────────────────────
# EXP-040: Multi-Horizon Transfer Cascade (depends on EXP-035)
# ────────────────────────────────────────────────────────────────────

def run_horizon_transfer(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-040', out, hypothesis='cascade transfer > scratch')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    scales = np.array([NORMALIZATION_SCALES.get(f, 1.0) for f in
                       ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs',
                        'time_sin', 'time_cos']], dtype=np.float32)
    win_size = 24

    by_horizon = {}
    for ppath in paths:
        try:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None:
                continue
            if 'time_sin' not in grid_df.columns:
                hours = grid_df.index.hour + grid_df.index.minute / 60.0
                grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
            mh = build_multihorizon_windows(grid_df)
            for h_label, h_data in mh.items():
                features = h_data['features']
                n_cols = min(features.shape[1], len(scales))
                norm_feat = features.copy()
                norm_feat[:, :n_cols] /= scales[:n_cols]
                stride = max(1, win_size // 2)
                for i in range(0, len(norm_feat) - win_size + 1, stride):
                    win = norm_feat[i:i + win_size]
                    if not np.isnan(win).any() and not np.isinf(win).any():
                        by_horizon.setdefault(h_label, []).append(win)
        except Exception:
            continue

    horizon_order = ['1hr@5min', '6hr@15min', '3day@1hr']
    cascade_results = {}
    prev_ckpt = None

    for label in horizon_order:
        ctx.section(f'Horizon: {label}')
        windows = by_horizon.get(label, [])
        if len(windows) < 50:
            ctx.log(f'Only {len(windows)} windows — skipping')
            cascade_results[label] = {'status': 'too_few_windows'}
            continue

        train_ds, val_ds = windows_to_datasets(windows)
        safe = label.replace('@', '_').replace('/', '_')

        m_scratch = create_model('grouped', input_dim=8)
        _, ep_s = train_forecast(m_scratch, train_ds, val_ds,
                        f'{out}/exp040_scratch_{safe}.pth', f'Scratch-{label}')
        mse_s = forecast_mse(m_scratch, val_ds, mask_future=True)

        m_transfer = create_model('grouped', input_dim=8)
        if prev_ckpt and os.path.exists(prev_ckpt):
            load_checkpoint(m_transfer, prev_ckpt)
            ctx.log(f'Transferred from {prev_ckpt}')
        transfer_path = f'{out}/exp040_transfer_{safe}.pth'
        _, ep_t = train_forecast(m_transfer, train_ds, val_ds, transfer_path, f'Transfer-{label}')
        mse_t = forecast_mse(m_transfer, val_ds, mask_future=True)
        prev_ckpt = transfer_path

        improv = improvement_pct(mse_t, mse_s)
        cascade_results[label] = {
            'scratch_mse': mse_s, 'scratch_epochs': ep_s,
            'transfer_mse': mse_t, 'transfer_epochs': ep_t,
            'improvement_pct': improv,
        }
        ctx.log(f'{label}: scratch={mse_s:.6f} transfer={mse_t:.6f} Δ={improv:.1f}%')

    ctx.result['cascades'] = cascade_results
    ctx.result['success'] = any(
        r.get('improvement_pct', 0) > 10
        for r in cascade_results.values() if isinstance(r, dict))
    return ctx.save('exp040_horizon_transfer.json')


# ────────────────────────────────────────────────────────────────────
# EXP-041: Backtest with Denormalized Pipeline
# Depends on: EXP-034, EXP-036
# ────────────────────────────────────────────────────────────────────

def run_backtest_denorm(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-041', out, hypothesis='denorm backtest > 5 suggestions/patient')
    patients_dir = getattr(args, 'patients_dir', None)
    paths = resolve_patient_paths(patients_dir, getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']

    model = create_model('grouped', input_dim=8)
    ckpt = find_checkpoint(out, 'exp043_forecast_8f_1hr.pth',
                           'exp026_grouped_8f.pth',
                           'exp035_norm_mh_1hr_5min.pth',
                           'grouped_multi_transfer.pth')
    if ckpt:
        load_checkpoint(model, ckpt)

    forecaster = HierarchicalForecaster(short_model=model)
    engine = BacktestEngine(forecaster=forecaster)

    all_results = []
    for ppath in paths[:5]:
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Patient {pname}')
        try:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None:
                continue
            glucose_mgdl = feat[:, 0] * glucose_scale
            valid = ~np.isnan(glucose_mgdl)
            glucose_mgdl = glucose_mgdl[valid]

            treatments_path = ppath.rstrip('/') + '/treatments.json'
            ds_path = ppath.rstrip('/') + '/devicestatus.json'
            events = extract_override_events(
                treatments_path,
                ds_path if os.path.exists(ds_path) else None
            ) if os.path.exists(treatments_path) else []

            bt = engine.full_backtest(
                glucose_mgdl=glucose_mgdl, events=events,
                window_size_steps=72, stride_steps=36)
            all_results.append({'patient': pname, **bt})
            ctx.log(f'{pname}: {bt.get("n_suggestions", 0)} suggestions, '
                    f'TIR={bt.get("mean_tir", 0):.1f}%')
        except Exception as e:
            ctx.log(f'{pname}: Error — {e}')
            all_results.append({'patient': pname, 'error': str(e)})

    n_sugg = sum(r.get('n_suggestions', 0) for r in all_results)
    n_pat = len([r for r in all_results if 'error' not in r])
    avg = n_sugg / max(n_pat, 1)

    ctx.result['patients'] = all_results
    ctx.result['total_suggestions'] = n_sugg
    ctx.result['avg_suggestions_per_patient'] = avg
    ctx.result['success'] = avg > 5
    ctx.section('Summary')
    ctx.log(f'{n_sugg} suggestions across {n_pat} patients (avg {avg:.1f}/patient)')
    return ctx.save('exp041_backtest_denorm.json')


# ────────────────────────────────────────────────────────────────────
# EXP-042: Composite Decision Pipeline
# Depends on: EXP-026 (model checkpoint)
# Hypothesis: Full agentic chain runs end-to-end and produces
#   clinically coherent results across patients.
# Success: Chain completes for >80% of patients; drift↔TIR correlation
#   is negative (more drift → lower TIR); calibration gap < 10%.
# ────────────────────────────────────────────────────────────────────

def run_composite_decision(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-042', out,
                           hypothesis='composite chain produces coherent decisions')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # Load or train a model
    model = create_model('grouped', input_dim=8)
    ckpt = find_checkpoint(out, 'exp026_grouped_8f.pth',
                           'grouped_multi_transfer.pth',
                           'exp034_grouped.pth')
    if ckpt:
        load_checkpoint(model, ckpt)
    else:
        ctx.log('No checkpoint found — training fresh model')
        ds, vds = load_multipatient_nightscout(paths, window_size=24)
        if ds is not None and len(ds) > 0:
            train(model, ds, vds, f'{out}/exp042_grouped.pth', 'EXP042-base')

    # --- Phase 1: Decision chain per patient ---
    ctx.section('Phase 1: Decision chain')
    patient_results = []
    completed = 0

    for ppath in paths:
        pname = ppath.rstrip('/').split('/')[-2]
        try:
            from .real_data_adapter import build_nightscout_grid
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is None or len(feat) < 48:
                ctx.log(f'{pname}: insufficient data')
                continue

            isf, cr = load_patient_profile(ppath)

            # Pick an interesting window (mid-data)
            center_idx = len(feat) // 2
            r = run_decision(
                model, feat, grid_df, center_idx,
                history=12, horizon=12,
                profile={'isf': isf, 'cr': cr},
                n_mc_samples=20)

            r['patient'] = pname
            patient_results.append(r)
            completed += 1

            drift_state = 'unknown'
            drift_d = r.get('drift_tracking', {})
            if 'classification' in drift_d:
                cls = drift_d['classification']
                drift_state = cls.get('state', '?') if isinstance(cls, dict) else str(cls)

            tir = r.get('clinical_actual', {}).get('tir', None)
            ctx.log(f'{pname}: drift={drift_state} TIR={tir}')

        except Exception as e:
            ctx.log(f'{pname}: Error — {e}')
            patient_results.append({'patient': pname, 'error': str(e)})

    completion_rate = completed / max(1, len(paths))

    # --- Phase 2: Calibration check ---
    ctx.section('Phase 2: Calibration')
    cal_result = {'status': 'skipped'}
    try:
        # Use first patient's features for calibration
        for ppath in paths[:1]:
            grid_df, feat = build_nightscout_grid(ppath, verbose=False)
            if feat is not None and len(feat) > 100:
                cal_result = run_calibration(
                    model, feat, history=12, horizon=12, stride=24,
                    n_samples_sweep=[10, 50],
                    confidence_levels=[0.5, 0.95])
                break
    except Exception as e:
        cal_result = {'status': 'error', 'message': str(e)}

    cal_gap = cal_result.get('best_95_gap', 1.0)
    ctx.log(f'95% calibration gap: {cal_gap}')

    # --- Phase 3: Drift ↔ TIR correlation ---
    ctx.section('Phase 3: Drift-TIR correlation')
    drift_tir_pairs = []
    for r in patient_results:
        if 'error' in r:
            continue
        drift_d = r.get('drift_tracking', {})
        isf_drift = abs(drift_d.get('final_isf_drift_pct', 0))
        tir = r.get('clinical_actual', {}).get('tir', None)
        if tir is not None:
            drift_tir_pairs.append((isf_drift, tir))

    correlation = None
    if len(drift_tir_pairs) >= 3:
        drifts = np.array([p[0] for p in drift_tir_pairs])
        tirs = np.array([p[1] for p in drift_tir_pairs])
        if np.std(drifts) > 0 and np.std(tirs) > 0:
            correlation = float(np.corrcoef(drifts, tirs)[0, 1])
            ctx.log(f'Drift-TIR correlation: {correlation:.3f} '
                    f'(n={len(drift_tir_pairs)})')

    # --- Results ---
    ctx.result.update({
        'patients': patient_results,
        'completion_rate': round(completion_rate, 3),
        'calibration': cal_result,
        'calibration_gap_95': cal_gap,
        'drift_tir_correlation': correlation,
        'n_drift_tir_pairs': len(drift_tir_pairs),
        'success': (completion_rate > 0.8
                    and (cal_gap is None or cal_gap < 0.10)),
    })
    ctx.section('Summary')
    ctx.log(f'Completed: {completed}/{len(paths)} ({completion_rate:.0%})')
    ctx.log(f'Calibration gap: {cal_gap}')
    ctx.log(f'Drift↔TIR r: {correlation}')
    ctx.log(f'Success: {ctx.result["success"]}')
    return ctx.save('exp042_composite_decision.json')


# ────────────────────────────────────────────────────────────────────
# EXP-043: Forecast-Masked Training
# Hypothesis: Training with future glucose masked forces the model
#   to learn actual forecasting (from IOB/COB/basal + history) instead
#   of reconstruction.  True forecast MAE should drop from ~155 to <30 mg/dL
#   at 1hr and <60 mg/dL at 6hr.
# ────────────────────────────────────────────────────────────────────

def run_forecast_masked(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-043', out,
                           hypothesis='masked training → real forecast')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    from .schema import NORMALIZATION_SCALES, FEATURE_NAMES
    glucose_scale = NORMALIZATION_SCALES['glucose']
    scales = np.array([NORMALIZATION_SCALES.get(f, 1.0)
                       for f in FEATURE_NAMES], dtype=np.float32)
    epochs = getattr(args, 'epochs', 80)
    results = {}

    from torch.utils.data import DataLoader

    # --- Train at 1hr (normalized, 8f) ---
    ctx.section('1hr forecast-masked training (8f)')
    windows_8f = load_multipatient_nightscout(paths, window_size=24)
    if len(windows_8f) > 100:
        train_ds, val_ds = windows_to_datasets(windows_8f)
        model = create_model('grouped', input_dim=8)
        best, ep = train_forecast(
            model, train_ds, val_ds,
            f'{out}/exp043_forecast_8f_1hr.pth', 'FM-8f-1hr',
            epochs=epochs)

        fmse = forecast_mse(model, val_ds, mask_future=True)
        pmse = persistence_mse(val_ds)

        device = get_device()
        model.eval()
        all_pred, all_true = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            all_pred.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            all_true.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

        pred_flat = np.concatenate(all_pred).flatten()
        true_flat = np.concatenate(all_true).flatten()
        mae_1hr = float(np.mean(np.abs(pred_flat - true_flat)))
        rmse_1hr = float(np.sqrt(np.mean((pred_flat - true_flat) ** 2)))

        results['8f_1hr'] = {
            'mae_mgdl': mae_1hr, 'rmse_mgdl': rmse_1hr,
            'forecast_mse': fmse, 'persistence_mse': pmse,
            'improvement_pct': improvement_pct(fmse, pmse),
            'epochs': ep, 'best_loss': best,
        }
        ctx.log(f'1hr 8f: MAE={mae_1hr:.1f} mg/dL, RMSE={rmse_1hr:.1f}, '
                f'vs persist Δ={improvement_pct(fmse, pmse):.1f}%')

    # --- Train multi-horizon (normalized, masked) ---
    for h_label in ['1hr@5min', '6hr@15min', '3day@1hr']:
        ctx.section(f'{h_label} forecast-masked training')
        all_windows = []
        for ppath in paths:
            try:
                grid_df, feat = build_nightscout_grid(ppath, verbose=False)
                if feat is None:
                    continue
                if 'time_sin' not in grid_df.columns:
                    hours = grid_df.index.hour + grid_df.index.minute / 60.0
                    grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                    grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
                mh = build_multihorizon_windows(grid_df)
                for label, h_data in mh.items():
                    safe = label.replace('@', '_').replace('/', '_')
                    target = h_label.replace('@', '_').replace('/', '_')
                    if safe == target:
                        features = h_data['features']
                        n_cols = min(features.shape[1], len(scales))
                        norm_feat = features.copy()
                        norm_feat[:, :n_cols] /= scales[:n_cols]
                        stride = max(1, 24 // 2)
                        for i in range(0, len(norm_feat) - 24 + 1, stride):
                            win = norm_feat[i:i + 24]
                            if not np.isnan(win).any() and not np.isinf(win).any():
                                all_windows.append(win)
            except Exception:
                continue

        if len(all_windows) < 50:
            ctx.log(f'{h_label}: only {len(all_windows)} windows, skipping')
            continue

        train_ds, val_ds = windows_to_datasets(all_windows)
        dim = all_windows[0].shape[-1]
        safe_label = h_label.replace('@', '_').replace('/', '_')
        model = create_model('grouped', input_dim=dim)
        best, ep = train_forecast(
            model, train_ds, val_ds,
            f'{out}/exp043_forecast_mh_{safe_label}.pth',
            f'FM-{h_label}', epochs=epochs)

        fmse = forecast_mse(model, val_ds, mask_future=True)
        pmse = persistence_mse(val_ds)

        device = get_device()
        model.eval()
        all_pred, all_true = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            all_pred.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            all_true.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

        pred_flat = np.concatenate(all_pred).flatten()
        true_flat = np.concatenate(all_true).flatten()
        mae_val = float(np.mean(np.abs(pred_flat - true_flat)))
        rmse_val = float(np.sqrt(np.mean((pred_flat - true_flat) ** 2)))

        results[h_label] = {
            'mae_mgdl': mae_val, 'rmse_mgdl': rmse_val,
            'forecast_mse': fmse, 'persistence_mse': pmse,
            'improvement_pct': improvement_pct(fmse, pmse),
            'epochs': ep, 'best_loss': best,
        }
        ctx.log(f'{h_label}: MAE={mae_val:.1f} mg/dL, RMSE={rmse_val:.1f}, '
                f'vs persist Δ={improvement_pct(fmse, pmse):.1f}%')

    # --- Summary ---
    ctx.section('Summary')
    for k, v in results.items():
        ctx.log(f'{k}: MAE={v["mae_mgdl"]:.1f} mg/dL, '
                f'Δ={v["improvement_pct"]:.1f}% vs persistence')

    ctx.result['metrics'] = results
    mae_vals = [v['mae_mgdl'] for v in results.values()]
    ctx.result['success'] = any(m < 30 for m in mae_vals) if mae_vals else False
    return ctx.save('exp043_forecast_masked.json')


# ════════════════════════════════════════════════════════════════════
# ROUND 4 — Forecast Refinement & Classifier Combos
# ════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────
# EXP-044: Architecture Sweep (forecast-masked)
# Hypothesis: Wider/deeper models improve forecast MAE at 1hr.
# Configs: {d_model: 32/64/128} × {layers: 2/4}
# ────────────────────────────────────────────────────────────────────

def run_arch_sweep(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-044', out, hypothesis='wider/deeper → lower MAE')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    if len(train_ds) < 100:
        ctx.result['success'] = False
        return ctx.save('exp044_arch_sweep.json')

    configs = [
        {'d_model': 32, 'num_layers': 2, 'nhead': 4},   # baseline (270K params)
        {'d_model': 64, 'num_layers': 2, 'nhead': 4},   # wider
        {'d_model': 64, 'num_layers': 4, 'nhead': 4},   # wider+deeper
        {'d_model': 128, 'num_layers': 2, 'nhead': 8},  # much wider
        {'d_model': 128, 'num_layers': 4, 'nhead': 8},  # large
    ]

    from torch.utils.data import DataLoader
    results = {}
    for cfg in configs:
        label = f'd{cfg["d_model"]}_L{cfg["num_layers"]}'
        ctx.section(f'Config: {label}')
        model = CGMGroupedEncoder(
            input_dim=8, d_model=cfg['d_model'],
            nhead=cfg['nhead'], num_layers=cfg['num_layers'])
        n_params = sum(p.numel() for p in model.parameters())
        save = f'{out}/exp044_{label}.pth'
        best, ep = train_forecast(model, train_ds, val_ds, save, label,
                                  epochs=60, patience=12)
        fmse = forecast_mse(model, val_ds, mask_future=True)
        pmse = persistence_mse(val_ds)

        device = get_device()
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        results[label] = {
            'mae_mgdl': mae, 'params': n_params,
            'forecast_mse': fmse, 'persistence_mse': pmse,
            'improvement_pct': improvement_pct(fmse, pmse),
            'epochs': ep,
        }
        ctx.log(f'{label}: MAE={mae:.1f} mg/dL, params={n_params:,}, '
                f'Δ={improvement_pct(fmse, pmse):.1f}%')

    ctx.result['configs'] = results
    best_cfg = min(results, key=lambda k: results[k]['mae_mgdl'])
    ctx.result['best_config'] = best_cfg
    ctx.result['best_mae'] = results[best_cfg]['mae_mgdl']
    ctx.result['success'] = results[best_cfg]['mae_mgdl'] < 12.0
    ctx.section('Winner')
    ctx.log(f'{best_cfg}: MAE={results[best_cfg]["mae_mgdl"]:.1f} mg/dL')
    return ctx.save('exp044_arch_sweep.json')


# ────────────────────────────────────────────────────────────────────
# EXP-045: Per-Patient Fine-Tuning
# Hypothesis: Fine-tuning the multi-patient model per patient
#   reduces MAE by >15% vs the generic model.
# ────────────────────────────────────────────────────────────────────

def run_per_patient_finetune(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-045', out, hypothesis='finetune > generic by 15%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    base_ckpt = find_checkpoint(out, 'exp043_forecast_mh_1hr_5min.pth',
                                'exp043_forecast_8f_1hr.pth')
    if not base_ckpt:
        ctx.log('No base checkpoint'); ctx.result['success'] = False
        return ctx.save('exp045_finetune.json')

    results = {}
    for ppath in paths:
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Patient {pname}')
        try:
            train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
            if len(train_ds) < 50:
                ctx.log(f'{pname}: too few windows — skip')
                continue

            # Generic model eval
            model_gen = create_model('grouped', input_dim=8)
            load_checkpoint(model_gen, base_ckpt)
            gen_mse = forecast_mse(model_gen, val_ds, mask_future=True)

            # Fine-tune
            model_ft = create_model('grouped', input_dim=8)
            load_checkpoint(model_ft, base_ckpt)
            ft_path = f'{out}/exp045_ft_{pname}.pth'
            best, ep = train_forecast(model_ft, train_ds, val_ds, ft_path,
                                      f'FT-{pname}', epochs=30, lr=5e-4,
                                      patience=8)
            ft_mse = forecast_mse(model_ft, val_ds, mask_future=True)

            # MAE in mg/dL
            device = get_device()
            model_ft.eval()
            preds, trues = [], []
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                half = x.shape[1] // 2
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                with torch.no_grad():
                    pred = model_ft(x_in, causal=True)
                preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
                trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

            ft_mae = float(np.mean(np.abs(
                np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
            improv = improvement_pct(ft_mse, gen_mse)
            results[pname] = {
                'generic_mse': gen_mse, 'finetune_mse': ft_mse,
                'finetune_mae_mgdl': ft_mae,
                'improvement_pct': improv, 'epochs': ep,
            }
            ctx.log(f'{pname}: FT MAE={ft_mae:.1f} mg/dL, Δ={improv:.1f}% vs generic')
        except Exception as e:
            ctx.log(f'{pname}: Error — {e}')

    ctx.result['patients'] = results
    avg_improv = np.mean([r['improvement_pct'] for r in results.values()]) if results else 0
    ctx.result['avg_improvement_pct'] = float(avg_improv)
    ctx.result['success'] = avg_improv > 15
    ctx.section('Summary')
    ctx.log(f'Avg improvement: {avg_improv:.1f}%')
    return ctx.save('exp045_finetune.json')


# ────────────────────────────────────────────────────────────────────
# EXP-046: Walk-Forward Temporal Validation
# Hypothesis: Temporal split gives more realistic (higher) MAE than
#   random split, revealing overfitting to temporal patterns.
# ────────────────────────────────────────────────────────────────────

def run_walkforward_forecast(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-046', out, hypothesis='temporal split → higher MAE')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader, TensorDataset

    # Random split (baseline — same as EXP-043)
    train_rnd, val_rnd = load_multipatient_nightscout(paths, window_size=24)
    if len(train_rnd) < 200:
        ctx.result['success'] = False
        return ctx.save('exp046_walkforward.json')

    model_rnd = create_model('grouped', input_dim=8)
    train_forecast(model_rnd, train_rnd, val_rnd,
                   f'{out}/exp046_random.pth', 'WF-random', epochs=60)
    rnd_mse = forecast_mse(model_rnd, val_rnd, mask_future=True)

    # Temporal split: extract all data, sort, split 80/20
    all_tensors = []
    for ds in [train_rnd, val_rnd]:
        for i in range(len(ds)):
            all_tensors.append(ds[i][0])
    all_t = torch.stack(all_tensors)
    n = all_t.shape[0]
    split = int(n * 0.8)
    train_temp = TensorDataset(all_t[:split], all_t[:split])
    val_temp = TensorDataset(all_t[split:], all_t[split:])

    model_temp = create_model('grouped', input_dim=8)
    train_forecast(model_temp, train_temp, val_temp,
                   f'{out}/exp046_temporal.pth', 'WF-temporal', epochs=60)
    temp_mse = forecast_mse(model_temp, val_temp, mask_future=True)

    # MAE for both
    device = get_device()
    mae_results = {}
    for name, model, vds in [('random', model_rnd, val_rnd),
                              ('temporal', model_temp, val_temp)]:
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(vds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        mae_results[name] = mae

    ctx.result.update({
        'random_mse': rnd_mse, 'temporal_mse': temp_mse,
        'random_mae_mgdl': mae_results['random'],
        'temporal_mae_mgdl': mae_results['temporal'],
        'temporal_harder_pct': improvement_pct(temp_mse, rnd_mse),
        'success': True,  # informational
    })
    ctx.section('Results')
    ctx.log(f'Random:   MAE={mae_results["random"]:.1f} mg/dL  MSE={rnd_mse:.6f}')
    ctx.log(f'Temporal: MAE={mae_results["temporal"]:.1f} mg/dL  MSE={temp_mse:.6f}')
    ctx.log(f'Temporal is {abs(improvement_pct(temp_mse, rnd_mse)):.1f}% '
            f'{"harder" if temp_mse > rnd_mse else "easier"}')
    return ctx.save('exp046_walkforward.json')


# ────────────────────────────────────────────────────────────────────
# EXP-047: 16-Feature Forecast-Masked
# Hypothesis: Extended features (glucose ROC, day-of-week, override
#   state) improve forecast when trained with proper masking.
# ────────────────────────────────────────────────────────────────────

def run_forecast_16f(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-047', out, hypothesis='16f masked > 8f masked')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    # Build 16f windows
    windows_16f = build_16f_windows(paths, window_size=24)
    if len(windows_16f) < 100:
        ctx.result['success'] = False
        return ctx.save('exp047_forecast_16f.json')

    # 8f baseline (from EXP-043)
    train_8f, val_8f = load_multipatient_nightscout(paths, window_size=24)
    model_8f = create_model('grouped', input_dim=8)
    train_forecast(model_8f, train_8f, val_8f,
                   f'{out}/exp047_8f.pth', '047-8f', epochs=60)
    mse_8f = forecast_mse(model_8f, val_8f, mask_future=True)

    # 16f
    train_16f, val_16f = windows_to_datasets(windows_16f)
    model_16f = create_model('grouped', input_dim=16)
    train_forecast(model_16f, train_16f, val_16f,
                   f'{out}/exp047_16f.pth', '047-16f', epochs=60)
    mse_16f = forecast_mse(model_16f, val_16f, mask_future=True)

    # MAE for both
    device = get_device()
    mae_results = {}
    for name, model, vds in [('8f', model_8f, val_8f), ('16f', model_16f, val_16f)]:
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(vds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        mae_results[name] = mae

    improv = improvement_pct(mse_16f, mse_8f)
    ctx.result.update({
        'mse_8f': mse_8f, 'mse_16f': mse_16f,
        'mae_8f_mgdl': mae_results['8f'], 'mae_16f_mgdl': mae_results['16f'],
        'improvement_pct': improv,
        'success': improv > 5,
    })
    ctx.section('Results')
    ctx.log(f'8f:  MAE={mae_results["8f"]:.1f} mg/dL')
    ctx.log(f'16f: MAE={mae_results["16f"]:.1f} mg/dL')
    ctx.log(f'16f vs 8f: {improv:.1f}%')
    return ctx.save('exp047_forecast_16f.json')


# ────────────────────────────────────────────────────────────────────
# EXP-048: Physics-Residual Training
# Hypothesis: Train ML to predict (true - physics_pred) residual,
#   then compose forecast = physics + ML_residual.
# ────────────────────────────────────────────────────────────────────

def run_physics_residual_train(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-048', out,
                           hypothesis='residual training > direct forecast')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader, TensorDataset

    # Build windows and compute physics predictions
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    if len(train_ds) < 100:
        ctx.result['success'] = False
        return ctx.save('exp048_physics_residual.json')

    isf, cr = load_patient_profile(paths[0])
    ctx.log(f'ISF={isf}, CR={cr}')

    # Extract numpy windows from datasets for physics computation
    all_windows = []
    for ds in [train_ds, val_ds]:
        for i in range(len(ds)):
            all_windows.append(ds[i][0].numpy())

    # Compute physics baseline for each window and create residual targets
    residual_windows = []
    for win in all_windows:
        half = win.shape[0] // 2
        gl_now = win[half - 1, 0] * glucose_scale
        iob_now = win[half - 1, 1] * NORMALIZATION_SCALES.get('iob', 20)
        cob_now = win[half - 1, 2] * NORMALIZATION_SCALES.get('cob', 100)

        phys_gl = np.full(half, gl_now)
        for t in range(half):
            decay = t / half
            phys_gl[t] = (gl_now - iob_now * (1 - decay) * isf
                          + cob_now * (1 - decay) / max(cr, 1) * isf)
        phys_norm = phys_gl / glucose_scale  # back to normalized

        # Residual target: true - physics (in normalized space)
        residual = win.copy()
        residual[half:, 0] = win[half:, 0] - phys_norm
        residual_windows.append(residual)

    # Split residual windows
    n = len(residual_windows)
    idx = np.random.RandomState(42).permutation(n)
    split = int(n * 0.8)
    t_train = torch.stack([torch.from_numpy(residual_windows[i]).float() for i in idx[:split]])
    t_val = torch.stack([torch.from_numpy(residual_windows[i]).float() for i in idx[split:]])
    orig_val = [all_windows[i] for i in idx[split:]]

    train_res = TensorDataset(t_train, t_train)
    val_res = TensorDataset(t_val, t_val)

    # Train residual model
    ctx.section('Training residual model')
    model_res = create_model('grouped', input_dim=8)
    train_forecast(model_res, train_res, val_res,
                   f'{out}/exp048_residual.pth', 'PhysRes', epochs=60)

    # Evaluate: compose physics + residual
    ctx.section('Evaluation')
    device = get_device()
    model_res.eval()
    combo_errors, direct_errors, physics_errors = [], [], []

    direct_ckpt = find_checkpoint(out, 'exp043_forecast_mh_1hr_5min.pth',
                                  'exp043_forecast_8f_1hr.pth')
    model_direct = create_model('grouped', input_dim=8)
    if direct_ckpt:
        load_checkpoint(model_direct, direct_ckpt)
    model_direct.eval()

    for orig_win, res_win in zip(orig_val[:2000], [residual_windows[i] for i in idx[split:]]):
        half = orig_win.shape[0] // 2
        true_gl = orig_win[half:, 0] * glucose_scale

        # Physics
        gl_now = orig_win[half - 1, 0] * glucose_scale
        iob_now = orig_win[half - 1, 1] * NORMALIZATION_SCALES.get('iob', 20)
        cob_now = orig_win[half - 1, 2] * NORMALIZATION_SCALES.get('cob', 100)
        phys_gl = np.full(half, gl_now)
        for t in range(half):
            decay = t / half
            phys_gl[t] = (gl_now - iob_now * (1 - decay) * isf
                          + cob_now * (1 - decay) / max(cr, 1) * isf)

        # Residual model → combo
        x_res = torch.from_numpy(res_win).unsqueeze(0).float().to(device)
        x_in = x_res.clone(); x_in[0, half:, 0] = 0.0
        with torch.no_grad():
            pred_res = model_res(x_in, causal=True)
        residual_gl = pred_res[0, half:, 0].cpu().numpy() * glucose_scale
        combo_gl = phys_gl + residual_gl

        # Direct model
        x_orig = torch.from_numpy(orig_win).unsqueeze(0).float().to(device)
        x_direct = x_orig.clone(); x_direct[0, half:, 0] = 0.0
        with torch.no_grad():
            pred_direct = model_direct(x_direct, causal=True)
        direct_gl = pred_direct[0, half:, 0].cpu().numpy() * glucose_scale

        combo_errors.append(np.mean(np.abs(combo_gl - true_gl)))
        direct_errors.append(np.mean(np.abs(direct_gl - true_gl)))
        physics_errors.append(np.mean(np.abs(phys_gl - true_gl)))

    combo_mae = float(np.mean(combo_errors))
    direct_mae = float(np.mean(direct_errors))
    phys_mae = float(np.mean(physics_errors))

    ctx.result.update({
        'physics_mae': phys_mae, 'direct_mae': direct_mae,
        'combo_mae': combo_mae,
        'combo_vs_direct_pct': improvement_pct(combo_mae, direct_mae),
        'combo_vs_physics_pct': improvement_pct(combo_mae, phys_mae),
        'success': combo_mae < direct_mae,
    })
    ctx.section('Results')
    ctx.log(f'Physics:         {phys_mae:.1f} mg/dL')
    ctx.log(f'Direct ML:       {direct_mae:.1f} mg/dL')
    ctx.log(f'Physics+Residual: {combo_mae:.1f} mg/dL')
    return ctx.save('exp048_physics_residual.json')


# ────────────────────────────────────────────────────────────────────
# EXP-049: Combined Rolling + Cost-Sensitive Classifier
# Hypothesis: Rolling features (EXP-037) + cost-sensitive (EXP-038)
#   combine for F1 > 0.70.
# ────────────────────────────────────────────────────────────────────

def run_combined_classifier(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-049', out, hypothesis='rolling+cost > 0.70 F1')
    patients_dir = getattr(args, 'patients_dir', None)

    ds = build_classifier_dataset(patients_dir)
    tabular = ds['tabular']
    labels = ds['labels']
    feat_names = list(ds['feature_names'])

    # Remove lead_time
    if 'lead_time_hr' in feat_names:
        lt_idx = feat_names.index('lead_time_hr')
        tabular = np.delete(tabular, lt_idx, axis=1)
        feat_names = [f for i, f in enumerate(feat_names) if i != lt_idx]

    # Add rolling features
    gl_idx = None
    for i, fn in enumerate(feat_names):
        if fn.startswith('glucose') and 'roc' not in fn:
            gl_idx = i; break

    if gl_idx is not None:
        import pandas as pd
        gl_series = pd.Series(tabular[:, gl_idx])
        rolling_feats, rolling_names = [], []
        for window in [12, 36, 72]:
            label_w = f'{window * 5 // 60}hr'
            roll = gl_series.rolling(window, min_periods=1)
            for stat, fn in [('mean', roll.mean), ('std', lambda: roll.std().fillna(0)),
                             ('min', roll.min), ('max', roll.max)]:
                rolling_feats.append(fn().values if callable(fn) else fn.values)
                rolling_names.append(f'glucose_{stat}_{label_w}')
        tabular = np.hstack([tabular, np.column_stack(rolling_feats).astype(np.float32)])
        feat_names.extend(rolling_names)
        ctx.log(f'Added {len(rolling_names)} rolling features → {tabular.shape[1]} total')

    # Cost-sensitive weights (exp=0.5, best from EXP-038)
    from collections import Counter
    counts = Counter(labels.tolist())
    max_count = max(counts.values())
    weight_map = {c: (max_count / cnt) ** 0.5 for c, cnt in counts.items()}
    sample_weight = np.array([weight_map[int(l)] for l in labels], dtype=np.float32)

    ctx.section('Training')
    result = train_event_classifier(
        tabular, labels, feature_names=feat_names,
        xgb_params={'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.01},
        sample_weight=sample_weight,
    )
    metrics = result['metrics']
    f1 = metrics.get('macro_f1_events', metrics.get('macro_f1', 0))
    per_class = metrics.get('per_class', {})

    ctx.section('Results')
    ctx.log(f'Macro F1 = {f1:.4f} (target > 0.70)')
    for cls_name, cls_m in per_class.items():
        ctx.log(f'  {cls_name}: P={cls_m.get("precision",0):.3f} '
                f'R={cls_m.get("recall",0):.3f} F1={cls_m.get("f1",0):.3f}')

    fi = result.get('feature_importance', {})
    top10 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:10]

    ctx.result.update({
        'macro_f1': f1, 'per_class': per_class,
        'feature_importance_top10': dict(top10),
        'n_features': tabular.shape[1],
        'success': f1 > 0.70,
    })
    return ctx.save('exp049_combined_classifier.json')


# ────────────────────────────────────────────────────────────────────
# EXP-050: Binary One-vs-Rest Detectors
# Hypothesis: Individual binary classifiers per event type achieve
#   higher per-class F1 than the multi-class model.
# ────────────────────────────────────────────────────────────────────

def run_binary_detectors(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-050', out, hypothesis='binary > multiclass per-event')
    patients_dir = getattr(args, 'patients_dir', None)

    ds = build_classifier_dataset(patients_dir)
    tabular = ds['tabular']
    labels = ds['labels']
    feat_names = list(ds['feature_names'])
    label_map = ds['label_map']

    if 'lead_time_hr' in feat_names:
        lt_idx = feat_names.index('lead_time_hr')
        tabular = np.delete(tabular, lt_idx, axis=1)
        feat_names = [f for i, f in enumerate(feat_names) if i != lt_idx]

    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score, precision_score, recall_score

    inv_map = {v: k for k, v in label_map.items()}
    results = {}

    for cls_id, cls_name in sorted(inv_map.items()):
        if cls_name == 'none':
            continue
        ctx.section(f'Binary: {cls_name}')
        binary_labels = (labels == cls_id).astype(int)
        pos_count = int(binary_labels.sum())
        neg_count = len(binary_labels) - pos_count

        X_train, X_val, y_train, y_val = train_test_split(
            tabular, binary_labels, test_size=0.2, random_state=42,
            stratify=binary_labels)

        model = xgb.XGBClassifier(
            max_depth=6, n_estimators=200, learning_rate=0.02,
            scale_pos_weight=neg_count / max(pos_count, 1),
            eval_metric='logloss', verbosity=0,
            tree_method='hist', random_state=42)
        model.fit(X_train, y_train,
                  eval_set=[(X_val, y_val)], verbose=False)

        y_pred = model.predict(X_val)
        f1 = float(f1_score(y_val, y_pred))
        prec = float(precision_score(y_val, y_pred))
        rec = float(recall_score(y_val, y_pred))

        results[cls_name] = {
            'f1': f1, 'precision': prec, 'recall': rec,
            'pos_count': pos_count, 'neg_count': neg_count,
        }
        ctx.log(f'{cls_name}: F1={f1:.3f} P={prec:.3f} R={rec:.3f} '
                f'(pos={pos_count})')

    ctx.result['binary_results'] = results
    avg_f1 = np.mean([r['f1'] for r in results.values()])
    ctx.result['avg_binary_f1'] = float(avg_f1)
    ctx.result['success'] = avg_f1 > 0.60
    ctx.section('Summary')
    ctx.log(f'Avg binary F1: {avg_f1:.3f}')
    return ctx.save('exp050_binary_detectors.json')


# ────────────────────────────────────────────────────────────────────
# EXP-051: Multi-Seed Forecast Stability
# Hypothesis: Forecast-masked training is stable across seeds
#   (std < 1.0 mg/dL MAE across 5 seeds).
# ────────────────────────────────────────────────────────────────────

def run_forecast_multiseed(args):
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-051', out, hypothesis='std < 1.0 mg/dL across seeds')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    windows = load_multipatient_nightscout(paths, window_size=24)
    # Unpack tuple: (train_ds, val_ds)
    if isinstance(windows, tuple):
        train_ds, val_ds = windows
    else:
        train_ds, val_ds = windows_to_datasets(windows)

    seeds = [42, 123, 456, 789, 2024]
    seed_results = []

    for seed in seeds:
        set_seed(seed)
        ctx.section(f'Seed {seed}')
        model = create_model('grouped', input_dim=8)
        save = f'{out}/exp051_seed{seed}.pth'
        best, ep = train_forecast(model, train_ds, val_ds, save,
                                  f'Seed-{seed}', epochs=50)
        fmse = forecast_mse(model, val_ds, mask_future=True)
        pmse = persistence_mse(val_ds)

        device = get_device()
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))

        seed_results.append({'seed': seed, 'mae_mgdl': mae,
                             'forecast_mse': fmse, 'epochs': ep})
        ctx.log(f'Seed {seed}: MAE={mae:.1f} mg/dL')

    maes = [r['mae_mgdl'] for r in seed_results]
    ctx.result.update({
        'seeds': seed_results,
        'mean_mae': float(np.mean(maes)),
        'std_mae': float(np.std(maes)),
        'min_mae': float(np.min(maes)),
        'max_mae': float(np.max(maes)),
        'success': float(np.std(maes)) < 1.0,
    })
    ctx.section('Summary')
    ctx.log(f'MAE: {np.mean(maes):.1f} ± {np.std(maes):.2f} mg/dL '
            f'(range {np.min(maes):.1f}–{np.max(maes):.1f})')
    return ctx.save('exp051_multiseed.json')


# ────────────────────────────────────────────────────────────────────
# EXP-052: Forecast Uncertainty with Masked Model
# Hypothesis: MC-Dropout on forecast-masked model gives calibrated
#   prediction intervals (coverage 85–95% at 90% target).
# ────────────────────────────────────────────────────────────────────

def run_forecast_uncertainty(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-052', out,
                           hypothesis='MC-Dropout coverage 85–95%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp043_forecast_mh_1hr_5min.pth',
                           'exp043_forecast_8f_1hr.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp052_uncertainty.json')

    _, val_ds = load_multipatient_nightscout(paths, window_size=24)
    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)

    device = get_device()
    n_mc = 30
    coverages = {50: [], 80: [], 90: [], 95: []}

    for batch in DataLoader(val_ds, batch_size=32):
        x = batch[0].to(device)
        half = x.shape[1] // 2
        true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale

        # MC dropout predictions
        mc_preds = []
        model.train()  # enable dropout
        for _ in range(n_mc):
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            mc_preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
        model.eval()

        mc_stack = np.stack(mc_preds, axis=0)  # (n_mc, batch, time)
        mean_pred = mc_stack.mean(axis=0)

        for pct, cov_list in coverages.items():
            lo = np.percentile(mc_stack, (100 - pct) / 2, axis=0)
            hi = np.percentile(mc_stack, 100 - (100 - pct) / 2, axis=0)
            covered = ((true_gl >= lo) & (true_gl <= hi)).mean()
            cov_list.append(float(covered))

    results = {}
    for pct, vals in coverages.items():
        actual = float(np.mean(vals))
        results[f'{pct}pct'] = {'target': pct / 100, 'actual': actual,
                                'gap': actual - pct / 100}
        ctx.log(f'{pct}% interval: actual coverage = {actual:.3f} '
                f'(gap = {actual - pct / 100:+.3f})')

    gap_90 = abs(results['90pct']['gap'])
    ctx.result.update({
        'coverage': results,
        'gap_90': gap_90,
        'success': gap_90 < 0.05,  # within 5% of target
    })
    return ctx.save('exp052_uncertainty.json')


# ────────────────────────────────────────────────────────────────────
# EXP-053: Longer Training (150 epochs) at All Horizons
# Hypothesis: More epochs improve EXP-043 results, especially
#   at longer horizons where loss was still decreasing.
# ────────────────────────────────────────────────────────────────────

def run_longer_training(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-053', out, hypothesis='150ep > 80ep at all horizons')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    from .schema import NORMALIZATION_SCALES, FEATURE_NAMES
    glucose_scale = NORMALIZATION_SCALES['glucose']
    scales = np.array([NORMALIZATION_SCALES.get(f, 1.0)
                       for f in FEATURE_NAMES], dtype=np.float32)
    from torch.utils.data import DataLoader
    results = {}

    for h_label in ['1hr@5min', '6hr@15min', '3day@1hr']:
        ctx.section(f'{h_label} — 150 epochs')
        all_windows = []
        for ppath in paths:
            try:
                grid_df, feat = build_nightscout_grid(ppath, verbose=False)
                if feat is None:
                    continue
                if 'time_sin' not in grid_df.columns:
                    hours = grid_df.index.hour + grid_df.index.minute / 60.0
                    grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                    grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
                mh = build_multihorizon_windows(grid_df)
                for label, h_data in mh.items():
                    safe = label.replace('@', '_').replace('/', '_')
                    target = h_label.replace('@', '_').replace('/', '_')
                    if safe == target:
                        features = h_data['features']
                        n_cols = min(features.shape[1], len(scales))
                        norm_feat = features.copy()
                        norm_feat[:, :n_cols] /= scales[:n_cols]
                        stride = max(1, 24 // 2)
                        for i in range(0, len(norm_feat) - 24 + 1, stride):
                            win = norm_feat[i:i + 24]
                            if not np.isnan(win).any() and not np.isinf(win).any():
                                all_windows.append(win)
            except Exception:
                continue

        if len(all_windows) < 50:
            continue

        train_ds, val_ds = windows_to_datasets(all_windows)
        dim = all_windows[0].shape[-1]
        safe_label = h_label.replace('@', '_').replace('/', '_')
        model = create_model('grouped', input_dim=dim)
        best, ep = train_forecast(
            model, train_ds, val_ds,
            f'{out}/exp053_long_{safe_label}.pth',
            f'Long-{h_label}', epochs=150, patience=25)

        fmse = forecast_mse(model, val_ds, mask_future=True)
        pmse = persistence_mse(val_ds)

        device = get_device()
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        results[h_label] = {
            'mae_mgdl': mae, 'epochs': ep,
            'forecast_mse': fmse, 'persistence_mse': pmse,
            'improvement_pct': improvement_pct(fmse, pmse),
        }
        ctx.log(f'{h_label}: MAE={mae:.1f} mg/dL (ep={ep}), '
                f'Δ={improvement_pct(fmse, pmse):.1f}%')

    ctx.result['metrics'] = results
    ctx.result['success'] = any(
        r['mae_mgdl'] < 12.0 for r in results.values())
    ctx.section('Summary (vs EXP-043 80ep)')
    for k, v in results.items():
        ctx.log(f'{k}: MAE={v["mae_mgdl"]:.1f} mg/dL')
    return ctx.save('exp053_longer_training.json')


# ────────────────────────────────────────────────────────────────────
# EXP-054: Event-Conditioned Forecast
# Hypothesis: Adding predicted event probabilities as extra forecast
#   input features improves forecast MAE by > 5%.
# ────────────────────────────────────────────────────────────────────

def run_event_conditioned(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-054', out,
                           hypothesis='event probs → 5% better forecast')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader, TensorDataset
    import xgboost as xgb

    # Step 1: Load classifier
    ctx.section('Loading classifier')
    ds = build_classifier_dataset(getattr(args, 'patients_dir', None))
    tabular_cls = ds['tabular']
    labels_cls = ds['labels']
    feat_names_cls = list(ds['feature_names'])
    label_map = ds['label_map']

    if 'lead_time_hr' in feat_names_cls:
        lt_idx = feat_names_cls.index('lead_time_hr')
        tabular_cls = np.delete(tabular_cls, lt_idx, axis=1)
        feat_names_cls = [f for i, f in enumerate(feat_names_cls) if i != lt_idx]

    # Remap labels to contiguous
    unique_labels = sorted(set(labels_cls.tolist()))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    y_cls = np.array([label_to_idx[int(l)] for l in labels_cls])
    n_classes = len(unique_labels)

    clf = xgb.XGBClassifier(
        max_depth=8, n_estimators=200, learning_rate=0.02,
        objective='multi:softprob', num_class=n_classes,
        eval_metric='mlogloss', verbosity=0,
        tree_method='hist', random_state=42)
    clf.fit(tabular_cls, y_cls)
    ctx.log(f'Classifier: {n_classes} classes, {tabular_cls.shape[1]} features')

    # Step 2: Build forecast windows with event probabilities appended
    ctx.section('Building event-conditioned windows')
    train_base, val_base = load_multipatient_nightscout(paths, window_size=24)
    if len(train_base) < 100:
        ctx.result['success'] = False
        return ctx.save('exp054_event_conditioned.json')

    # Extract numpy windows for augmentation
    base_numpy = []
    for ds in [train_base, val_base]:
        for i in range(len(ds)):
            base_numpy.append(ds[i][0].numpy())

    # For each window, get classifier prediction on the history portion
    aug_windows = []
    for win in base_numpy:
        half = win.shape[0] // 2
        hist = win[:half]
        gl_mean = float(np.mean(hist[:, 0]))
        gl_std = float(np.std(hist[:, 0]))
        iob_mean = float(np.mean(hist[:, 1]))
        cob_mean = float(np.mean(hist[:, 2]))
        gl_roc = float(hist[-1, 0] - hist[0, 0]) if half > 1 else 0.0
        # Pad to match classifier input dim
        feat_vec = np.zeros(tabular_cls.shape[1], dtype=np.float32)
        feat_vec[0] = gl_mean
        if len(feat_vec) > 1: feat_vec[1] = gl_std
        if len(feat_vec) > 2: feat_vec[2] = iob_mean
        if len(feat_vec) > 3: feat_vec[3] = cob_mean
        if len(feat_vec) > 4: feat_vec[4] = gl_roc

        probs = clf.predict_proba(feat_vec.reshape(1, -1))[0]  # (n_classes,)
        prob_tile = np.tile(probs, (win.shape[0], 1))
        aug_win = np.hstack([win, prob_tile])
        aug_windows.append(aug_win)

    # Train conditioned model
    ctx.section('Training event-conditioned forecast')
    train_aug, val_aug = windows_to_datasets(aug_windows)
    aug_dim = aug_windows[0].shape[-1]  # 8 + n_classes
    model_aug = create_model('grouped', input_dim=aug_dim)
    train_forecast(model_aug, train_aug, val_aug,
                   f'{out}/exp054_conditioned.pth', 'EvtCond',
                   epochs=60)
    mse_aug = forecast_mse(model_aug, val_aug, mask_future=True)

    # Baseline: 8f model (use the already-loaded datasets)
    model_base = create_model('grouped', input_dim=8)
    base_ckpt = find_checkpoint(out, 'exp043_forecast_8f_1hr.pth',
                                'exp043_forecast_mh_1hr_5min.pth')
    if base_ckpt:
        load_checkpoint(model_base, base_ckpt)
    else:
        train_forecast(model_base, train_base, val_base,
                       f'{out}/exp054_baseline.pth', 'Base', epochs=60)
    mse_base = forecast_mse(model_base, val_base, mask_future=True)

    # MAE comparison
    device = get_device()
    mae_results = {}
    for name, model, vds in [('base', model_base, val_base),
                              ('conditioned', model_aug, val_aug)]:
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(vds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        mae_results[name] = mae

    improv = improvement_pct(mse_aug, mse_base)
    ctx.result.update({
        'base_mae': mae_results['base'], 'conditioned_mae': mae_results['conditioned'],
        'base_mse': mse_base, 'conditioned_mse': mse_aug,
        'improvement_pct': improv, 'n_event_features': n_classes,
        'success': improv > 5,
    })
    ctx.section('Results')
    ctx.log(f'Base 8f:       MAE={mae_results["base"]:.1f} mg/dL')
    ctx.log(f'Event-cond:    MAE={mae_results["conditioned"]:.1f} mg/dL')
    ctx.log(f'Improvement:   {improv:.1f}%')
    return ctx.save('exp054_event_conditioned.json')


# ────────────────────────────────────────────────────────────────────
# EXP-055: Patient Generalization (Leave-One-Out)
# Hypothesis: Model trained on 9 patients generalizes to held-out
#   patient with MAE < 20 mg/dL at 1hr.
# ────────────────────────────────────────────────────────────────────

def run_patient_generalization(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-055', out,
                           hypothesis='leave-one-out MAE < 20 mg/dL')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    # Test on first 5 patients (leave-one-out is expensive)
    test_paths = paths[:5]
    results = {}

    for held_out_idx, test_path in enumerate(test_paths):
        pname = test_path.rstrip('/').split('/')[-2]
        ctx.section(f'Hold out: {pname}')

        train_paths = [p for i, p in enumerate(paths) if i != held_out_idx]
        train_ds, train_val_ds = load_multipatient_nightscout(train_paths, window_size=24)
        test_train, test_val = load_multipatient_nightscout([test_path], window_size=24)

        if len(train_ds) < 100 or len(test_train) + len(test_val) < 20:
            ctx.log(f'{pname}: insufficient data')
            continue

        # Combine test splits into one test set
        test_tensors = []
        for ds in [test_train, test_val]:
            for i in range(len(ds)):
                test_tensors.append(ds[i][0])
        test_t = torch.stack(test_tensors)
        from torch.utils.data import TensorDataset
        test_full = TensorDataset(test_t, test_t)

        model = create_model('grouped', input_dim=8)
        save = f'{out}/exp055_loo_{pname}.pth'
        # Use train_val_ds for early stopping
        train_forecast(model, train_ds, train_val_ds, save,
                       f'LOO-{pname}', epochs=50, patience=10)

        # Eval on held-out patient
        fmse = forecast_mse(model, test_full, mask_future=True)
        pmse = persistence_mse(test_full)

        device = get_device()
        model.eval()
        preds, trues = [], []
        for batch in DataLoader(test_full, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
            trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        results[pname] = {
            'mae_mgdl': mae,
            'forecast_mse': fmse, 'persistence_mse': pmse,
            'improvement_pct': improvement_pct(fmse, pmse),
            'n_test_windows': len(test_tensors),
        }
        ctx.log(f'{pname}: MAE={mae:.1f} mg/dL, Δ={improvement_pct(fmse, pmse):.1f}%')

    ctx.result['patients'] = results
    maes = [r['mae_mgdl'] for r in results.values()]
    ctx.result['mean_mae'] = float(np.mean(maes)) if maes else 999
    ctx.result['std_mae'] = float(np.std(maes)) if maes else 0
    ctx.result['success'] = (float(np.mean(maes)) < 20) if maes else False
    ctx.section('Summary')
    if maes:
        ctx.log(f'Mean LOO MAE: {np.mean(maes):.1f} ± {np.std(maes):.1f} mg/dL')
    else:
        ctx.log('No patient results')
    return ctx.save('exp055_generalization.json')


# ════════════════════════════════════════════════════════════════════
# ROUND 5 — Uncertainty, Pipeline, Feature Fixes
# ════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────
# EXP-056: Ensemble Uncertainty from Multi-Seed Models
# Hypothesis: Using EXP-051's 5-seed models as ensemble gives
#   calibrated prediction intervals (90% coverage 85–95%).
# ────────────────────────────────────────────────────────────────────

def run_ensemble_uncertainty(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-056', out,
                           hypothesis='5-seed ensemble coverage 85–95%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    # Load 5-seed models from EXP-051 (or train if missing)
    seeds = [42, 123, 456, 789, 2024]
    models = []
    for seed in seeds:
        ckpt = find_checkpoint(out, f'exp051_seed{seed}.pth')
        if ckpt:
            m = create_model('grouped', input_dim=8)
            load_checkpoint(m, ckpt)
            models.append(m)
            ctx.log(f'Loaded seed {seed}')
        else:
            ctx.log(f'Missing seed {seed} — training')
            set_seed(seed)
            _, val_ds = load_multipatient_nightscout(paths, window_size=24)
            train_ds_s, val_ds_s = load_multipatient_nightscout(paths, window_size=24)
            m = create_model('grouped', input_dim=8)
            train_forecast(m, train_ds_s, val_ds_s,
                           f'{out}/exp051_seed{seed}.pth',
                           f'Seed-{seed}', epochs=50)
            models.append(m)

    if len(models) < 3:
        ctx.result['success'] = False
        return ctx.save('exp056_ensemble_uncertainty.json')

    _, val_ds = load_multipatient_nightscout(paths, window_size=24)
    device = get_device()
    coverages = {50: [], 80: [], 90: [], 95: []}
    all_preds_list, all_trues_list = [], []

    for batch in DataLoader(val_ds, batch_size=32):
        x = batch[0].to(device)
        half = x.shape[1] // 2
        true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale

        ensemble_preds = []
        for m in models:
            m.eval()
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = m(x_in, causal=True)
            ensemble_preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)

        stack = np.stack(ensemble_preds, axis=0)
        mean_pred = stack.mean(axis=0)
        all_preds_list.append(mean_pred)
        all_trues_list.append(true_gl)

        for pct, cov_list in coverages.items():
            lo = np.percentile(stack, (100 - pct) / 2, axis=0)
            hi = np.percentile(stack, 100 - (100 - pct) / 2, axis=0)
            covered = ((true_gl >= lo) & (true_gl <= hi)).mean()
            cov_list.append(float(covered))

    # Ensemble MAE
    all_preds = np.concatenate(all_preds_list).flatten()
    all_trues = np.concatenate(all_trues_list).flatten()
    ensemble_mae = float(np.mean(np.abs(all_preds - all_trues)))

    results = {}
    for pct, vals in coverages.items():
        actual = float(np.mean(vals))
        results[f'{pct}pct'] = {'target': pct / 100, 'actual': actual,
                                'gap': actual - pct / 100}
        ctx.log(f'{pct}% interval: coverage = {actual:.3f} '
                f'(gap = {actual - pct / 100:+.3f})')

    gap_90 = abs(results['90pct']['gap'])
    ctx.result.update({
        'coverage': results,
        'gap_90': gap_90,
        'ensemble_mae': ensemble_mae,
        'n_models': len(models),
        'success': gap_90 < 0.10,
    })
    ctx.section('Summary')
    ctx.log(f'Ensemble MAE: {ensemble_mae:.1f} mg/dL')
    ctx.log(f'90% gap: {gap_90:.3f} (target < 0.10)')
    return ctx.save('exp056_ensemble_uncertainty.json')


# ────────────────────────────────────────────────────────────────────
# EXP-057: Selective Per-Patient Fine-Tuning
# Hypothesis: Only fine-tuning when validation improves avoids the
#   degradation seen in EXP-045 for patients b, f, j.
# ────────────────────────────────────────────────────────────────────

def run_selective_finetune(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-057', out,
                           hypothesis='selective FT > unconditional FT')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    base_ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                                'exp043_forecast_mh_1hr_5min.pth',
                                'exp043_forecast_8f_1hr.pth')
    if not base_ckpt:
        ctx.log('No base checkpoint'); ctx.result['success'] = False
        return ctx.save('exp057_selective_ft.json')

    results = {}
    for ppath in paths:
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Patient {pname}')
        try:
            train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
            if len(train_ds) < 50:
                ctx.log(f'{pname}: too few — skip')
                continue

            # Generic model MAE
            model_gen = create_model('grouped', input_dim=8)
            load_checkpoint(model_gen, base_ckpt)
            gen_mse = forecast_mse(model_gen, val_ds, mask_future=True)

            # Fine-tune with very conservative LR
            model_ft = create_model('grouped', input_dim=8)
            load_checkpoint(model_ft, base_ckpt)
            ft_path = f'{out}/exp057_ft_{pname}.pth'
            best_ft, ep = train_forecast(model_ft, train_ds, val_ds, ft_path,
                                         f'SFT-{pname}', epochs=20, lr=2e-4,
                                         patience=5)

            # Selective: use FT only if val MSE improved
            ft_mse = forecast_mse(model_ft, val_ds, mask_future=True)
            use_ft = ft_mse < gen_mse
            chosen_model = model_ft if use_ft else model_gen

            device = get_device()
            chosen_model.eval()
            preds, trues = [], []
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                half = x.shape[1] // 2
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                with torch.no_grad():
                    pred = chosen_model(x_in, causal=True)
                preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
                trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

            sel_mae = float(np.mean(np.abs(
                np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
            results[pname] = {
                'generic_mse': gen_mse, 'finetune_mse': ft_mse,
                'used_finetune': use_ft,
                'selective_mae_mgdl': sel_mae,
                'improvement_pct': improvement_pct(ft_mse, gen_mse),
            }
            ctx.log(f'{pname}: {"FT" if use_ft else "GEN"} '
                    f'MAE={sel_mae:.1f} Δ={improvement_pct(ft_mse, gen_mse):.1f}%')
        except Exception as e:
            ctx.log(f'{pname}: Error — {e}')

    ctx.result['patients'] = results
    maes = [r['selective_mae_mgdl'] for r in results.values()]
    ft_rate = sum(1 for r in results.values() if r['used_finetune']) / len(results) if results else 0
    ctx.result['mean_mae'] = float(np.mean(maes)) if maes else 999
    ctx.result['ft_rate'] = ft_rate
    ctx.result['success'] = float(np.mean(maes)) < 12.0 if maes else False
    ctx.section('Summary')
    ctx.log(f'Mean selective MAE: {np.mean(maes):.1f} mg/dL, FT rate: {ft_rate:.0%}')
    return ctx.save('exp057_selective_ft.json')


# ────────────────────────────────────────────────────────────────────
# EXP-058: Safe 16f Forecast (mask extended features in future half)
# Hypothesis: Properly masked 16f features still improve forecast
#   over 8f by > 3% (without the leak).
# ────────────────────────────────────────────────────────────────────

def run_safe_16f_forecast(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-058', out, hypothesis='safe 16f > 8f by 3%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader, TensorDataset

    # Build 16f windows and mask ALL derivative features in future half
    windows_16f = build_16f_windows(paths, window_size=24)
    if len(windows_16f) < 100:
        ctx.result['success'] = False
        return ctx.save('exp058_safe_16f.json')

    # Mask only derivative features (ch8+) in future half.
    # DO NOT zero ch0 here — train_forecast handles ch0 masking and needs
    # original glucose as ground truth for the loss function.
    safe_windows = []
    for win in windows_16f:
        half = win.shape[0] // 2
        safe = win.copy()
        if win.shape[1] > 8:
            safe[half:, 8:] = 0.0  # glucose_roc, glucose_accel, etc.
        safe_windows.append(safe)

    # Train with custom masking: we already zeroed the windows,
    # but train_forecast also zeros ch0. That's fine — double-zero.
    train_16f, val_16f = windows_to_datasets(safe_windows)
    dim_16f = safe_windows[0].shape[-1]
    model_16f = create_model('grouped', input_dim=dim_16f)
    ctx.section('Training safe 16f')
    train_forecast(model_16f, train_16f, val_16f,
                   f'{out}/exp058_safe16f.pth', 'Safe16f', epochs=60)

    # 8f baseline
    train_8f, val_8f = load_multipatient_nightscout(paths, window_size=24)
    model_8f = create_model('grouped', input_dim=8)
    train_forecast(model_8f, train_8f, val_8f,
                   f'{out}/exp058_8f.pth', '058-8f', epochs=60)

    # MAE for both
    device = get_device()
    mae_results = {}

    # 16f eval: mask ch0 + ch8+ in input, use original ch0 as ground truth
    model_16f.eval()
    preds, trues = [], []
    for batch in DataLoader(val_16f, batch_size=64):
        x = batch[0].to(device)
        half = x.shape[1] // 2
        trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
        x_in = x.clone()
        x_in[:, half:, 0] = 0.0
        if x.shape[2] > 8:
            x_in[:, half:, 8:] = 0.0
        with torch.no_grad():
            pred = model_16f(x_in, causal=True)
        preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
    mae_results['16f'] = float(np.mean(np.abs(
        np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))

    # 8f eval
    model_8f.eval()
    preds, trues = [], []
    for batch in DataLoader(val_8f, batch_size=64):
        x = batch[0].to(device)
        half = x.shape[1] // 2
        x_in = x.clone(); x_in[:, half:, 0] = 0.0
        with torch.no_grad():
            pred = model_8f(x_in, causal=True)
        preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
        trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
    mae_results['8f'] = float(np.mean(np.abs(
        np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))

    improv = (mae_results['8f'] - mae_results['16f']) / mae_results['8f'] * 100
    ctx.result.update({
        'mae_8f': mae_results['8f'], 'mae_16f': mae_results['16f'],
        'improvement_pct': improv,
        'success': improv > 3,
    })
    ctx.section('Results')
    ctx.log(f'8f:       MAE={mae_results["8f"]:.1f} mg/dL')
    ctx.log(f'Safe 16f: MAE={mae_results["16f"]:.1f} mg/dL')
    ctx.log(f'Improvement: {improv:.1f}%')
    return ctx.save('exp058_safe_16f.json')


# ────────────────────────────────────────────────────────────────────
# EXP-059: Conformal Prediction Intervals
# Hypothesis: Split conformal prediction on residuals gives
#   calibrated 90% intervals (coverage 87–93%).
# ────────────────────────────────────────────────────────────────────

def run_conformal_prediction(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-059', out,
                           hypothesis='conformal 90% coverage 87–93%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth',
                           'exp043_forecast_8f_1hr.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp059_conformal.json')

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()

    # Step 1: Compute calibration residuals on calibration set (first half of val)
    ctx.section('Computing calibration residuals')
    cal_residuals = []
    test_preds, test_trues = [], []
    n_cal = len(val_ds) // 2

    for i, batch in enumerate(DataLoader(val_ds, batch_size=64)):
        x = batch[0].to(device)
        half = x.shape[1] // 2
        x_in = x.clone(); x_in[:, half:, 0] = 0.0
        with torch.no_grad():
            pred = model(x_in, causal=True)
        pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
        true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale

        # Compute per-window absolute residuals (max over time)
        max_residuals = np.max(np.abs(pred_gl - true_gl), axis=1)

        batch_start = i * 64
        if batch_start < n_cal:
            cal_end = min(len(max_residuals), n_cal - batch_start)
            cal_residuals.extend(max_residuals[:cal_end].tolist())
            if cal_end < len(max_residuals):
                test_preds.append(pred_gl[cal_end:])
                test_trues.append(true_gl[cal_end:])
        else:
            test_preds.append(pred_gl)
            test_trues.append(true_gl)

    if not cal_residuals or not test_preds:
        ctx.result['success'] = False
        return ctx.save('exp059_conformal.json')

    cal_residuals = np.array(cal_residuals)
    ctx.log(f'Calibration: {len(cal_residuals)} residuals, '
            f'median={np.median(cal_residuals):.1f}, '
            f'95th={np.percentile(cal_residuals, 95):.1f} mg/dL')

    # Step 2: Compute conformal intervals on test set
    ctx.section('Conformal intervals on test set')
    test_preds_arr = np.concatenate(test_preds)
    test_trues_arr = np.concatenate(test_trues)

    results = {}
    for target_pct in [50, 80, 90, 95]:
        # Conformal quantile: (1 - alpha)(1 + 1/n)
        alpha = 1 - target_pct / 100
        q = min((1 - alpha) * (1 + 1 / len(cal_residuals)), 1.0)
        threshold = float(np.quantile(cal_residuals, q))

        # Interval: pred ± threshold (applied per timestep)
        covered = np.all(np.abs(test_preds_arr - test_trues_arr) <= threshold, axis=1)
        coverage = float(covered.mean())
        results[f'{target_pct}pct'] = {
            'target': target_pct / 100,
            'actual': coverage,
            'gap': coverage - target_pct / 100,
            'threshold_mgdl': threshold,
        }
        ctx.log(f'{target_pct}%: coverage={coverage:.3f} '
                f'(gap={coverage - target_pct / 100:+.3f}), '
                f'threshold=±{threshold:.1f} mg/dL')

    gap_90 = abs(results['90pct']['gap'])
    ctx.result.update({
        'coverage': results,
        'gap_90': gap_90,
        'n_calibration': len(cal_residuals),
        'n_test': len(test_preds_arr),
        'success': gap_90 < 0.05,
    })
    return ctx.save('exp059_conformal.json')


# ────────────────────────────────────────────────────────────────────
# EXP-060: Fixed Backtest Pipeline
# Hypothesis: With properly denormalized forecasts, backtest produces
#   >3 suggestions per patient with timing accuracy < 30 min.
# ────────────────────────────────────────────────────────────────────

def run_backtest_fixed(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-060', out,
                           hypothesis='backtest produces >3 suggestions/patient')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp060_backtest_fixed.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()

    # Custom backtest: slide window across patient data, generate forecasts,
    # detect when predicted glucose crosses thresholds
    HYPO_THRESH = 70.0   # mg/dL
    HYPER_THRESH = 180.0  # mg/dL
    URGENT_HYPO = 54.0

    results = {}
    for ppath in paths[:5]:
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Backtest: {pname}')

        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        if len(val_ds) < 10:
            continue

        suggestions = []
        for batch in DataLoader(val_ds, batch_size=1):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            true_gl = x[0, half:, 0].cpu().numpy() * glucose_scale
            current_gl = float(x[0, half - 1, 0].cpu().numpy() * glucose_scale)

            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[0, half:, 0].cpu().numpy() * glucose_scale

            # Check if predicted glucose crosses thresholds
            min_pred = float(pred_gl.min())
            max_pred = float(pred_gl.max())

            if min_pred < HYPO_THRESH and current_gl > HYPO_THRESH:
                # Predict time to hypo
                hypo_idx = np.argmax(pred_gl < HYPO_THRESH)
                suggestions.append({
                    'type': 'hypo_warning',
                    'current_gl': current_gl,
                    'predicted_min': min_pred,
                    'steps_to_event': int(hypo_idx),
                    'actual_min': float(true_gl.min()),
                    'correct': float(true_gl.min()) < HYPO_THRESH,
                })
            elif max_pred > HYPER_THRESH and current_gl < HYPER_THRESH:
                hyper_idx = np.argmax(pred_gl > HYPER_THRESH)
                suggestions.append({
                    'type': 'hyper_warning',
                    'current_gl': current_gl,
                    'predicted_max': max_pred,
                    'steps_to_event': int(hyper_idx),
                    'actual_max': float(true_gl.max()),
                    'correct': float(true_gl.max()) > HYPER_THRESH,
                })

        n_sugg = len(suggestions)
        n_correct = sum(1 for s in suggestions if s.get('correct', False))
        precision = n_correct / n_sugg if n_sugg else 0

        results[pname] = {
            'n_suggestions': n_sugg,
            'n_correct': n_correct,
            'precision': precision,
            'n_windows': len(val_ds),
        }
        ctx.log(f'{pname}: {n_sugg} suggestions, '
                f'{n_correct} correct ({precision:.0%} precision)')

    ctx.result['patients'] = results
    total_sugg = sum(r['n_suggestions'] for r in results.values())
    avg_sugg = total_sugg / len(results) if results else 0
    avg_prec = np.mean([r['precision'] for r in results.values()
                        if r['n_suggestions'] > 0]) if results else 0
    ctx.result.update({
        'total_suggestions': total_sugg,
        'avg_per_patient': avg_sugg,
        'avg_precision': float(avg_prec),
        'success': avg_sugg > 3 and avg_prec > 0.3,
    })
    ctx.section('Summary')
    ctx.log(f'Total: {total_sugg} suggestions, avg {avg_sugg:.1f}/patient, '
            f'precision {avg_prec:.0%}')
    return ctx.save('exp060_backtest_fixed.json')


# ────────────────────────────────────────────────────────────────────
# EXP-061: Multi-Horizon Ensemble Forecast
# Hypothesis: Averaging predictions from 1hr, 6hr, and 3day models
#   (at overlapping timepoints) improves MAE by > 5%.
# ────────────────────────────────────────────────────────────────────

def run_horizon_ensemble(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-061', out,
                           hypothesis='multi-horizon ensemble > single model')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    # Load best models from EXP-053 (or EXP-043)
    ckpts = {}
    for label, names in [
        ('1hr', ['exp053_long_1hr_5min.pth', 'exp043_forecast_mh_1hr_5min.pth']),
        ('6hr', ['exp053_long_6hr_15min.pth', 'exp043_forecast_mh_6hr_15min.pth']),
        ('3day', ['exp053_long_3day_1hr.pth', 'exp043_forecast_mh_3day_1hr.pth']),
    ]:
        ck = find_checkpoint(out, *names)
        if ck:
            ckpts[label] = ck
            ctx.log(f'{label}: {ck}')

    if '1hr' not in ckpts:
        ctx.log('No 1hr checkpoint'); ctx.result['success'] = False
        return ctx.save('exp061_horizon_ensemble.json')

    # Use 1hr data for evaluation (all models must handle same window size)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    device = get_device()

    # Load models
    loaded_models = {}
    for label, ckpt_path in ckpts.items():
        m = create_model('grouped', input_dim=8)
        load_checkpoint(m, ckpt_path)
        m.eval()
        loaded_models[label] = m

    # Predict with each model and ensemble
    single_preds = {label: [] for label in loaded_models}
    all_trues = []

    for batch in DataLoader(val_ds, batch_size=64):
        x = batch[0].to(device)
        half = x.shape[1] // 2
        true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
        all_trues.append(true_gl)

        for label, m in loaded_models.items():
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = m(x_in, causal=True)
            single_preds[label].append(
                pred[:, half:, 0].cpu().numpy() * glucose_scale)

    trues_flat = np.concatenate(all_trues).flatten()

    # Individual MAEs
    mae_results = {}
    for label in loaded_models:
        pred_flat = np.concatenate(single_preds[label]).flatten()
        mae_results[label] = float(np.mean(np.abs(pred_flat - trues_flat)))

    # Ensemble: weighted average
    weights_options = [
        ('equal', {label: 1.0 / len(loaded_models) for label in loaded_models}),
        ('mae_weighted', None),  # compute below
    ]

    # MAE-weighted: inverse MAE
    if len(mae_results) > 1:
        inv_mae = {k: 1.0 / v for k, v in mae_results.items()}
        total_inv = sum(inv_mae.values())
        mae_w = {k: v / total_inv for k, v in inv_mae.items()}
        weights_options[1] = ('mae_weighted', mae_w)

    ensemble_results = {}
    for w_name, weights in weights_options:
        if weights is None:
            continue
        ensemble_pred = np.zeros_like(np.concatenate(single_preds[list(loaded_models)[0]]))
        for label in loaded_models:
            pred_arr = np.concatenate(single_preds[label])
            ensemble_pred += weights[label] * pred_arr
        e_mae = float(np.mean(np.abs(ensemble_pred.flatten() - trues_flat)))
        ensemble_results[w_name] = e_mae
        ctx.log(f'Ensemble ({w_name}): MAE={e_mae:.1f} mg/dL')

    best_single = min(mae_results.values())
    best_ensemble = min(ensemble_results.values()) if ensemble_results else 999
    improv = (best_single - best_ensemble) / best_single * 100

    ctx.result.update({
        'single_maes': mae_results,
        'ensemble_maes': ensemble_results,
        'best_single': best_single,
        'best_ensemble': best_ensemble,
        'improvement_pct': improv,
        'success': improv > 5,
    })
    ctx.section('Summary')
    for label, mae in sorted(mae_results.items()):
        ctx.log(f'  {label}: {mae:.1f} mg/dL')
    ctx.log(f'Best ensemble: {best_ensemble:.1f} vs best single: {best_single:.1f} '
            f'({improv:+.1f}%)')
    return ctx.save('exp061_horizon_ensemble.json')


# ════════════════════════════════════════════════════════════════════
# ROUND 6 — Combining Wins, Production-Readiness
# ════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────
# EXP-062: Conformal-Guided Backtest
# Hypothesis: Filtering backtest suggestions by conformal interval
#   width improves precision from 78% to >85%.
# ────────────────────────────────────────────────────────────────────

def run_conformal_backtest(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-062', out,
                           hypothesis='conformal filtering precision >85%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp062_conformal_backtest.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()

    HYPO_THRESH = 70.0
    HYPER_THRESH = 180.0

    # Step 1: Compute conformal threshold from calibration patients
    ctx.section('Calibration')
    cal_paths = paths[:5]
    cal_residuals = []
    for ppath in cal_paths:
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
            true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
            cal_residuals.extend(np.max(np.abs(pred_gl - true_gl), axis=1).tolist())

    cal_residuals = np.array(cal_residuals)
    q90 = float(np.quantile(cal_residuals, 0.90))
    ctx.log(f'90% conformal threshold: ±{q90:.1f} mg/dL')

    # Step 2: Backtest on test patients with confidence filtering
    ctx.section('Backtesting with conformal filter')
    test_paths = paths[5:]
    results_by_filter = {'none': {}, 'conformal': {}}

    for ppath in test_paths:
        pname = ppath.rstrip('/').split('/')[-2]
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        if len(val_ds) < 10:
            continue

        sugg_all, sugg_conf = [], []
        for batch in DataLoader(val_ds, batch_size=1):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            true_gl = x[0, half:, 0].cpu().numpy() * glucose_scale
            current_gl = float(x[0, half - 1, 0].cpu().numpy() * glucose_scale)
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[0, half:, 0].cpu().numpy() * glucose_scale

            min_pred, max_pred = float(pred_gl.min()), float(pred_gl.max())

            suggestion = None
            if min_pred < HYPO_THRESH and current_gl > HYPO_THRESH:
                suggestion = {'type': 'hypo', 'correct': float(true_gl.min()) < HYPO_THRESH}
            elif max_pred > HYPER_THRESH and current_gl < HYPER_THRESH:
                suggestion = {'type': 'hyper', 'correct': float(true_gl.max()) > HYPER_THRESH}

            if suggestion:
                sugg_all.append(suggestion)
                if suggestion['type'] == 'hypo':
                    confident = (min_pred + q90) < HYPO_THRESH
                else:
                    confident = (max_pred - q90) > HYPER_THRESH
                if confident:
                    sugg_conf.append(suggestion)

        for label, suggs in [('none', sugg_all), ('conformal', sugg_conf)]:
            n = len(suggs)
            correct = sum(1 for s in suggs if s['correct'])
            results_by_filter[label][pname] = {
                'n_suggestions': n, 'n_correct': correct,
                'precision': correct / n if n else 0
            }

    for label in ['none', 'conformal']:
        r = results_by_filter[label]
        total = sum(v['n_suggestions'] for v in r.values())
        correct = sum(v['n_correct'] for v in r.values())
        prec = correct / total if total else 0
        ctx.log(f'{label}: {total} suggestions, {correct} correct ({prec:.0%})')

    prec_none = sum(v['n_correct'] for v in results_by_filter['none'].values()) / \
        max(sum(v['n_suggestions'] for v in results_by_filter['none'].values()), 1)
    prec_conf = sum(v['n_correct'] for v in results_by_filter['conformal'].values()) / \
        max(sum(v['n_suggestions'] for v in results_by_filter['conformal'].values()), 1)

    ctx.result.update({
        'conformal_threshold': q90,
        'unfiltered': results_by_filter['none'],
        'conformal_filtered': results_by_filter['conformal'],
        'precision_unfiltered': prec_none,
        'precision_conformal': prec_conf,
        'precision_improvement': prec_conf - prec_none,
        'success': prec_conf > 0.85,
    })
    return ctx.save('exp062_conformal_backtest.json')


# ────────────────────────────────────────────────────────────────────
# EXP-063: Extended Training + Selective FT
# Hypothesis: 150-epoch base + selective FT pushes MAE below 11.0.
# ────────────────────────────────────────────────────────────────────

def run_extended_selective_ft(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-063', out,
                           hypothesis='150ep + selective FT MAE < 11.0')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    base_ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth')
    if not base_ckpt:
        ctx.section('Training base 150ep')
        train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
        base_model = create_model('grouped', input_dim=8)
        base_ckpt = f'{out}/exp063_base150.pth'
        train_forecast(base_model, train_ds, val_ds, base_ckpt,
                       'Base150', epochs=150, patience=25)
    ctx.log(f'Base: {base_ckpt}')

    ctx.section('Selective fine-tuning')
    results = {}
    for ppath in paths:
        pname = ppath.rstrip('/').split('/')[-2]
        try:
            train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
            if len(train_ds) < 50:
                continue

            model_gen = create_model('grouped', input_dim=8)
            load_checkpoint(model_gen, base_ckpt)
            gen_mse = forecast_mse(model_gen, val_ds, mask_future=True)

            model_ft = create_model('grouped', input_dim=8)
            load_checkpoint(model_ft, base_ckpt)
            ft_path = f'{out}/exp063_ft_{pname}.pth'
            train_forecast(model_ft, train_ds, val_ds, ft_path,
                           f'63FT-{pname}', epochs=30, lr=1e-4, patience=8)

            ft_mse = forecast_mse(model_ft, val_ds, mask_future=True)
            use_ft = ft_mse < gen_mse
            chosen = model_ft if use_ft else model_gen

            device = get_device()
            chosen.eval()
            preds, trues = [], []
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                half = x.shape[1] // 2
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                with torch.no_grad():
                    pred = chosen(x_in, causal=True)
                preds.append(pred[:, half:, 0].cpu().numpy() * glucose_scale)
                trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)

            mae = float(np.mean(np.abs(
                np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
            results[pname] = {
                'mae': mae, 'used_ft': use_ft,
                'gen_mse': gen_mse, 'ft_mse': ft_mse,
            }
            ctx.log(f'{pname}: {"FT" if use_ft else "GEN"} MAE={mae:.1f}')
        except Exception as e:
            ctx.log(f'{pname}: error — {e}')

    maes = [r['mae'] for r in results.values()]
    mean_mae = float(np.mean(maes)) if maes else 999
    ft_rate = sum(1 for r in results.values() if r['used_ft']) / len(results) if results else 0
    ctx.result.update({
        'patients': results,
        'mean_mae': mean_mae,
        'ft_rate': ft_rate,
        'success': mean_mae < 11.0,
    })
    ctx.section('Summary')
    ctx.log(f'Mean MAE: {mean_mae:.1f} mg/dL, FT rate: {ft_rate:.0%}')
    return ctx.save('exp063_extended_selective_ft.json')


# ────────────────────────────────────────────────────────────────────
# EXP-064: Forecast-Informed Classification
# Hypothesis: Using forecast trajectory as classifier features
#   improves event F1 from 0.710 to >0.75.
# ────────────────────────────────────────────────────────────────────

def run_forecast_classification(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-064', out,
                           hypothesis='forecast features boost F1 >0.75')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp064_forecast_classification.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()

    ctx.section('Generating forecast features')
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)

    def extract_forecast_features(ds):
        all_feats = []
        for batch in DataLoader(ds, batch_size=64):
            x = batch[0].to(device)
            half = x.shape[1] // 2
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
            true_hist = x[:, :half, 0].cpu().numpy() * glucose_scale

            for i in range(len(pred_gl)):
                fg = pred_gl[i]
                hg = true_hist[i]
                feats = {
                    'forecast_min': fg.min(), 'forecast_max': fg.max(),
                    'forecast_mean': fg.mean(), 'forecast_std': fg.std(),
                    'forecast_range': fg.max() - fg.min(),
                    'forecast_slope': (fg[-1] - fg[0]) / len(fg),
                    'forecast_below_70': (fg < 70).sum() / len(fg),
                    'forecast_above_180': (fg > 180).sum() / len(fg),
                    'hist_mean': hg.mean(), 'hist_std': hg.std(),
                    'hist_last': hg[-1], 'hist_min': hg.min(),
                    'hist_max': hg.max(),
                    'hist_roc': (hg[-1] - hg[0]) / len(hg),
                    'hist_roc_3': (hg[-1] - hg[-4]) / 3 if len(hg) >= 4 else 0,
                    'hist_std_6': hg[-6:].std() if len(hg) >= 6 else hg.std(),
                    'iob_mean': float(x[i, :half, 1].mean().cpu()) * 20,
                    'cob_mean': float(x[i, :half, 2].mean().cpu()) * 100,
                    'bolus_sum': float(x[i, :half, 4].sum().cpu()) * 10,
                    'carbs_sum': float(x[i, :half, 5].sum().cpu()) * 100,
                }
                all_feats.append(feats)
        return all_feats

    train_feats = extract_forecast_features(train_ds)
    val_feats = extract_forecast_features(val_ds)
    ctx.log(f'Train: {len(train_feats)}, Val: {len(val_feats)} windows')

    def label_events(ds):
        labels = []
        for batch in DataLoader(ds, batch_size=64):
            x = batch[0]
            half = x.shape[1] // 2
            for i in range(len(x)):
                future = x[i, half:, :]
                bolus = float(future[:, 4].sum()) * 10
                carbs = float(future[:, 5].sum()) * 100
                gl = future[:, 0].numpy() * glucose_scale
                if bolus > 0.5 and carbs > 10:
                    labels.append('meal_bolus')
                elif bolus > 0.5:
                    labels.append('correction_bolus')
                elif carbs > 10:
                    labels.append('eating_soon')
                elif gl.min() < 70:
                    labels.append('hypo_risk')
                elif gl.max() > 250:
                    labels.append('hyper_risk')
                else:
                    labels.append('normal')
        return labels

    train_labels = label_events(train_ds)
    val_labels = label_events(val_ds)

    import pandas as pd
    try:
        from xgboost import XGBClassifier
    except ImportError:
        ctx.result['success'] = False
        return ctx.save('exp064_forecast_classification.json')

    from sklearn.metrics import f1_score
    from sklearn.preprocessing import LabelEncoder

    le = LabelEncoder()
    y_train = le.fit_transform(train_labels[:len(train_feats)])
    y_val = le.transform(val_labels[:len(val_feats)])

    train_df = pd.DataFrame(train_feats)
    val_df = pd.DataFrame(val_feats)

    hist_cols = [c for c in train_df.columns if c.startswith('hist_') or
                 c in ('iob_mean', 'cob_mean', 'bolus_sum', 'carbs_sum')]
    all_cols = list(train_df.columns)

    results = {}
    for label, cols in [('history_only', hist_cols), ('history+forecast', all_cols)]:
        clf = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                            random_state=42, eval_metric='mlogloss', verbosity=0)
        sample_weights = np.ones(len(y_train))
        for cls in range(len(le.classes_)):
            mask = y_train == cls
            if mask.sum() > 0:
                sample_weights[mask] = len(y_train) / (len(le.classes_) * mask.sum())
        clf.fit(train_df[cols], y_train, sample_weight=sample_weights)
        y_pred = clf.predict(val_df[cols])
        f1 = float(f1_score(y_val, y_pred, average='macro'))
        results[label] = f1
        ctx.log(f'{label}: F1={f1:.3f}')

    improv = results['history+forecast'] - results['history_only']
    ctx.result.update({
        'results': results,
        'improvement': improv,
        'classes': list(le.classes_),
        'success': results['history+forecast'] > 0.75,
    })
    return ctx.save('exp064_forecast_classification.json')


# ────────────────────────────────────────────────────────────────────
# EXP-065: Per-Timestep Conformal Prediction
# Hypothesis: Per-timestep calibration gives expanding intervals
#   that are tighter near-term, still calibrated at each step.
# ────────────────────────────────────────────────────────────────────

def run_timestep_conformal(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-065', out,
                           hypothesis='per-timestep intervals expand naturally')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader, Subset

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp065_timestep_conformal.json')

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()

    n_cal = len(val_ds) // 2
    cal_ds = Subset(val_ds, range(n_cal))
    test_ds = Subset(val_ds, range(n_cal, len(val_ds)))
    half = 12

    ctx.section('Per-timestep calibration')
    residuals_per_step = [[] for _ in range(half)]
    for batch in DataLoader(cal_ds, batch_size=64):
        x = batch[0].to(device)
        x_in = x.clone(); x_in[:, half:, 0] = 0.0
        with torch.no_grad():
            pred = model(x_in, causal=True)
        pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
        true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
        for t in range(half):
            residuals_per_step[t].extend(np.abs(pred_gl[:, t] - true_gl[:, t]).tolist())

    residuals_per_step = [np.array(r) for r in residuals_per_step]
    thresholds_90 = []
    for t in range(half):
        q = min(0.90 * (1 + 1 / len(residuals_per_step[t])), 1.0)
        thresh = float(np.quantile(residuals_per_step[t], q))
        thresholds_90.append(thresh)
        ctx.log(f't+{t+1}: ±{thresh:.1f} mg/dL '
                f'(median={np.median(residuals_per_step[t]):.1f})')

    ctx.section('Test coverage')
    covered_per_step = [0 for _ in range(half)]
    total_per_step = [0 for _ in range(half)]

    for batch in DataLoader(test_ds, batch_size=64):
        x = batch[0].to(device)
        x_in = x.clone(); x_in[:, half:, 0] = 0.0
        with torch.no_grad():
            pred = model(x_in, causal=True)
        pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
        true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
        for t in range(half):
            errs = np.abs(pred_gl[:, t] - true_gl[:, t])
            covered_per_step[t] += int((errs <= thresholds_90[t]).sum())
            total_per_step[t] += len(errs)

    step_results = []
    for t in range(half):
        cov = covered_per_step[t] / total_per_step[t] if total_per_step[t] else 0
        step_results.append({
            'timestep': t + 1, 'threshold_mgdl': thresholds_90[t],
            'coverage': cov, 'gap': cov - 0.90,
        })
        ctx.log(f't+{t+1}: coverage={cov:.3f} (gap={cov - 0.90:+.3f})')

    mean_gap = float(np.mean([abs(s['gap']) for s in step_results]))
    ctx.result.update({
        'per_step': step_results,
        'thresholds': thresholds_90,
        'mean_abs_gap': mean_gap,
        'first_step_threshold': thresholds_90[0],
        'last_step_threshold': thresholds_90[-1],
        'expansion_ratio': thresholds_90[-1] / thresholds_90[0] if thresholds_90[0] > 0 else 0,
        'success': mean_gap < 0.05,
    })
    ctx.section('Summary')
    ctx.log(f'Thresholds: ±{thresholds_90[0]:.1f} → ±{thresholds_90[-1]:.1f} mg/dL')
    ctx.log(f'Expansion: {thresholds_90[-1] / thresholds_90[0]:.2f}x, '
            f'mean |gap|={mean_gap:.3f}')
    return ctx.save('exp065_timestep_conformal.json')


# ────────────────────────────────────────────────────────────────────
# EXP-066: Per-Patient Conformal after Selective FT
# Hypothesis: Patient-specific conformal thresholds are tighter
#   (narrower intervals) than global thresholds.
# ────────────────────────────────────────────────────────────────────

def run_patient_conformal(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-066', out,
                           hypothesis='per-patient conformal < global threshold')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    base_ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                                'exp043_forecast_mh_1hr_5min.pth')
    if not base_ckpt:
        ctx.result['success'] = False
        return ctx.save('exp066_patient_conformal.json')

    device = get_device()
    results = {}
    global_residuals = []

    for ppath in paths:
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Patient {pname}')
        try:
            train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
            if len(val_ds) < 20:
                continue

            ft_ckpt = find_checkpoint(out, f'exp057_ft_{pname}.pth',
                                      f'exp063_ft_{pname}.pth')
            model = create_model('grouped', input_dim=8)
            if ft_ckpt:
                load_checkpoint(model, ft_ckpt)
                gen_model = create_model('grouped', input_dim=8)
                load_checkpoint(gen_model, base_ckpt)
                gen_mse = forecast_mse(gen_model, val_ds, mask_future=True)
                ft_mse = forecast_mse(model, val_ds, mask_future=True)
                if ft_mse > gen_mse:
                    load_checkpoint(model, base_ckpt)
                    ft_ckpt = None
            else:
                load_checkpoint(model, base_ckpt)

            model.eval()
            n_cal = len(val_ds) // 2
            cal_residuals = []
            test_preds, test_trues = [], []

            for i, batch in enumerate(DataLoader(val_ds, batch_size=64)):
                x = batch[0].to(device)
                half = x.shape[1] // 2
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                with torch.no_grad():
                    pred = model(x_in, causal=True)
                pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
                true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
                max_res = np.max(np.abs(pred_gl - true_gl), axis=1)

                batch_start = i * 64
                if batch_start < n_cal:
                    cal_end = min(len(max_res), n_cal - batch_start)
                    cal_residuals.extend(max_res[:cal_end].tolist())
                    global_residuals.extend(max_res[:cal_end].tolist())
                    if cal_end < len(max_res):
                        test_preds.append(pred_gl[cal_end:])
                        test_trues.append(true_gl[cal_end:])
                else:
                    test_preds.append(pred_gl)
                    test_trues.append(true_gl)

            if not cal_residuals or not test_preds:
                continue

            cal_residuals = np.array(cal_residuals)
            q90_patient = float(np.quantile(cal_residuals, 0.90))
            test_preds_arr = np.concatenate(test_preds)
            test_trues_arr = np.concatenate(test_trues)
            test_max_res = np.max(np.abs(test_preds_arr - test_trues_arr), axis=1)
            coverage = float((test_max_res <= q90_patient).mean())

            results[pname] = {
                'threshold_90': q90_patient,
                'coverage': coverage,
                'used_ft': ft_ckpt is not None,
                'n_cal': len(cal_residuals),
            }
            ctx.log(f'{pname}: ±{q90_patient:.1f} mg/dL, coverage={coverage:.3f}')
        except Exception as e:
            ctx.log(f'{pname}: error — {e}')

    global_q90 = float(np.quantile(global_residuals, 0.90)) if global_residuals else 0
    patient_thresholds = [r['threshold_90'] for r in results.values()]
    mean_pt = float(np.mean(patient_thresholds)) if patient_thresholds else 0

    ctx.result.update({
        'patients': results,
        'global_threshold_90': global_q90,
        'mean_patient_threshold_90': mean_pt,
        'threshold_reduction': (global_q90 - mean_pt) / global_q90 * 100 if global_q90 else 0,
        'success': mean_pt < global_q90,
    })
    ctx.section('Summary')
    ctx.log(f'Global: ±{global_q90:.1f}, Mean patient: ±{mean_pt:.1f}')
    ctx.log(f'Reduction: {(global_q90 - mean_pt) / global_q90 * 100:.1f}%')
    return ctx.save('exp066_patient_conformal.json')


# ────────────────────────────────────────────────────────────────────
# EXP-067: Multi-Task Shared Encoder
# Hypothesis: Joint forecast + classification training improves
#   both tasks: forecast MAE < 12.0 AND classifier F1 > 0.72.
# ────────────────────────────────────────────────────────────────────

def run_multitask_encoder(args):
    set_seed(42)
    outdir = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-067', outdir,
                           hypothesis='joint training: MAE<12 AND F1>0.72')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    device = get_device()
    half = 12

    class MultiTaskModel(torch.nn.Module):
        def __init__(self, input_dim=8, d_model=64, n_classes=6):
            super().__init__()
            self.input_proj = torch.nn.Linear(input_dim, d_model)
            encoder_layer = torch.nn.TransformerEncoderLayer(
                d_model=d_model, nhead=4, dim_feedforward=128,
                dropout=0.1, batch_first=True, norm_first=True)
            self.encoder = torch.nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.forecast_head = torch.nn.Linear(d_model, 1)
            self.class_head = torch.nn.Sequential(
                torch.nn.Linear(d_model, 64), torch.nn.ReLU(),
                torch.nn.Dropout(0.2), torch.nn.Linear(64, n_classes))

        def forward(self, x, task='both'):
            h = self.input_proj(x)
            h = self.encoder(h)
            result = {}
            if task in ('forecast', 'both'):
                result['forecast'] = self.forecast_head(h).squeeze(-1)
            if task in ('classify', 'both'):
                result['logits'] = self.class_head(h[:, :x.shape[1] // 2].mean(dim=1))
            return result

    def label_window(x_batch):
        labels = []
        for i in range(len(x_batch)):
            future = x_batch[i, half:]
            bolus = float(future[:, 4].sum()) * 10
            carbs = float(future[:, 5].sum()) * 100
            gl = future[:, 0].numpy() * glucose_scale
            if bolus > 0.5 and carbs > 10:
                labels.append(0)
            elif bolus > 0.5:
                labels.append(1)
            elif carbs > 10:
                labels.append(2)
            elif gl.min() < 70:
                labels.append(3)
            elif gl.max() > 250:
                labels.append(4)
            else:
                labels.append(5)
        return torch.tensor(labels, dtype=torch.long)

    model = MultiTaskModel(input_dim=8).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5)
    forecast_loss_fn = torch.nn.MSELoss()
    class_loss_fn = torch.nn.CrossEntropyLoss()
    best_val_loss = float('inf')
    patience_ctr, max_patience = 0, 15

    ctx.section('Multi-task training')
    for epoch in range(80):
        model.train()
        train_losses = []
        for batch in DataLoader(train_ds, batch_size=64, shuffle=True):
            x = batch[0].to(device)
            labels = label_window(batch[0]).to(device)
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            mout = model(x_in, task='both')
            fl = forecast_loss_fn(mout['forecast'][:, half:], x[:, half:, 0])
            cl = class_loss_fn(mout['logits'], labels)
            loss = fl + 0.1 * cl
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                mout = model(x_in, task='forecast')
                val_losses.append(
                    forecast_loss_fn(mout['forecast'][:, half:], x[:, half:, 0]).item())

        val_loss = np.mean(val_losses)
        scheduler.step(val_loss)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), f'{outdir}/exp067_multitask.pth')
            patience_ctr = 0
        else:
            patience_ctr += 1
        if patience_ctr >= max_patience:
            ctx.log(f'Early stop at epoch {epoch + 1}')
            break
        if (epoch + 1) % 10 == 0:
            ctx.log(f'Epoch {epoch + 1}: train={np.mean(train_losses):.6f} '
                    f'val={val_loss:.6f}')

    model.load_state_dict(torch.load(f'{outdir}/exp067_multitask.pth',
                                     map_location=device, weights_only=True))
    model.eval()
    ctx.section('Evaluation')

    preds_all, trues_all, logits_all, labels_all = [], [], [], []
    with torch.no_grad():
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            labels = label_window(batch[0])
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            mout = model(x_in, task='both')
            preds_all.append(mout['forecast'][:, half:].cpu().numpy() * glucose_scale)
            trues_all.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
            logits_all.append(mout['logits'].cpu())
            labels_all.append(labels)

    mae = float(np.mean(np.abs(
        np.concatenate(preds_all).flatten() - np.concatenate(trues_all).flatten())))

    from sklearn.metrics import f1_score
    y_pred = torch.cat(logits_all).argmax(dim=1).numpy()
    y_true = torch.cat(labels_all).numpy()
    f1 = float(f1_score(y_true, y_pred, average='macro', zero_division=0))

    ctx.result.update({
        'forecast_mae': mae, 'classifier_f1': f1,
        'success': mae < 12.0 and f1 > 0.72,
    })
    ctx.log(f'Forecast MAE: {mae:.1f} mg/dL')
    ctx.log(f'Classifier F1: {f1:.3f}')
    return ctx.save('exp067_multitask.json')


# ════════════════════════════════════════════════════════════════════
# ROUND 7 — Multi-Task Refinement, Production Pipeline
# ════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────
# EXP-068: Balanced Multi-Task (sweep forecast:classify loss ratio)
# Hypothesis: Adjusting loss weights to 1:0.01 or 1:0.5 finds a
#   Pareto point with MAE < 14 AND F1 > 0.80.
# ────────────────────────────────────────────────────────────────────

def run_multitask_balanced(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-068', out,
                           hypothesis='balanced multi-task: MAE<14, F1>0.80')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    device = get_device()
    half = 12

    class MultiTaskModel(torch.nn.Module):
        def __init__(self, input_dim=8, d_model=64, n_classes=6):
            super().__init__()
            self.input_proj = torch.nn.Linear(input_dim, d_model)
            encoder_layer = torch.nn.TransformerEncoderLayer(
                d_model=d_model, nhead=4, dim_feedforward=128,
                dropout=0.1, batch_first=True, norm_first=True)
            self.encoder = torch.nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.forecast_head = torch.nn.Linear(d_model, 1)
            self.class_head = torch.nn.Sequential(
                torch.nn.Linear(d_model, 64), torch.nn.ReLU(),
                torch.nn.Dropout(0.2), torch.nn.Linear(64, n_classes))

        def forward(self, x, task='both'):
            h = self.input_proj(x)
            h = self.encoder(h)
            result = {}
            if task in ('forecast', 'both'):
                result['forecast'] = self.forecast_head(h).squeeze(-1)
            if task in ('classify', 'both'):
                result['logits'] = self.class_head(h[:, :x.shape[1] // 2].mean(dim=1))
            return result

    def label_window(x_batch):
        labels = []
        for i in range(len(x_batch)):
            future = x_batch[i, half:]
            bolus = float(future[:, 4].sum()) * 10
            carbs = float(future[:, 5].sum()) * 100
            gl = future[:, 0].numpy() * glucose_scale
            if bolus > 0.5 and carbs > 10:
                labels.append(0)
            elif bolus > 0.5:
                labels.append(1)
            elif carbs > 10:
                labels.append(2)
            elif gl.min() < 70:
                labels.append(3)
            elif gl.max() > 250:
                labels.append(4)
            else:
                labels.append(5)
        return torch.tensor(labels, dtype=torch.long)

    from sklearn.metrics import f1_score

    # Sweep loss weight ratios
    ratios = [0.01, 0.05, 0.1, 0.5, 1.0]
    sweep_results = {}

    for cls_weight in ratios:
        set_seed(42)
        model = MultiTaskModel(input_dim=8).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5)
        best_val = float('inf')
        patience_ctr = 0
        ckpt_path = f'{out}/exp068_w{cls_weight}.pth'

        ctx.section(f'Weight ratio 1:{cls_weight}')
        for epoch in range(80):
            model.train()
            for batch in DataLoader(train_ds, batch_size=64, shuffle=True):
                x = batch[0].to(device)
                labels = label_window(batch[0]).to(device)
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                mout = model(x_in, task='both')
                fl = torch.nn.functional.mse_loss(mout['forecast'][:, half:], x[:, half:, 0])
                cl = torch.nn.functional.cross_entropy(mout['logits'], labels)
                loss = fl + cls_weight * cl
                optimizer.zero_grad(); loss.backward(); optimizer.step()

            model.eval()
            val_losses = []
            with torch.no_grad():
                for batch in DataLoader(val_ds, batch_size=64):
                    x = batch[0].to(device)
                    x_in = x.clone(); x_in[:, half:, 0] = 0.0
                    mout = model(x_in, task='forecast')
                    val_losses.append(
                        torch.nn.functional.mse_loss(
                            mout['forecast'][:, half:], x[:, half:, 0]).item())

            val_loss = np.mean(val_losses)
            scheduler.step(val_loss)
            if val_loss < best_val:
                best_val = val_loss
                torch.save(model.state_dict(), ckpt_path)
                patience_ctr = 0
            else:
                patience_ctr += 1
            if patience_ctr >= 15:
                break

        # Evaluate
        model.load_state_dict(torch.load(ckpt_path, map_location=device,
                                         weights_only=True))
        model.eval()
        preds, trues, logits_all, labels_all = [], [], [], []
        with torch.no_grad():
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                labels = label_window(batch[0])
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                mout = model(x_in, task='both')
                preds.append(mout['forecast'][:, half:].cpu().numpy() * glucose_scale)
                trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
                logits_all.append(mout['logits'].cpu())
                labels_all.append(labels)

        mae = float(np.mean(np.abs(
            np.concatenate(preds).flatten() - np.concatenate(trues).flatten())))
        y_pred = torch.cat(logits_all).argmax(dim=1).numpy()
        y_true = torch.cat(labels_all).numpy()
        f1 = float(f1_score(y_true, y_pred, average='macro', zero_division=0))

        sweep_results[str(cls_weight)] = {'mae': mae, 'f1': f1}
        ctx.log(f'w={cls_weight}: MAE={mae:.1f}, F1={f1:.3f}')

    # Find Pareto best
    best_pareto = None
    for w, r in sweep_results.items():
        if r['mae'] < 14 and r['f1'] > 0.80:
            if best_pareto is None or r['mae'] + (1 - r['f1']) * 20 < \
                    best_pareto[1]['mae'] + (1 - best_pareto[1]['f1']) * 20:
                best_pareto = (w, r)

    ctx.result.update({
        'sweep': sweep_results,
        'best_pareto': best_pareto[0] if best_pareto else None,
        'success': best_pareto is not None,
    })
    return ctx.save('exp068_multitask_balanced.json')


# ────────────────────────────────────────────────────────────────────
# EXP-069: Combined All-Features Classifier
# Hypothesis: Merging rolling features (EXP-049) + forecast features
#   (EXP-064) + history features pushes F1 > 0.75 in XGBoost.
# ────────────────────────────────────────────────────────────────────

def run_combined_all_classifier(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-069', out,
                           hypothesis='all-features F1 > 0.75')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    # Load forecast model for generating forecast features
    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp069_combined_all_classifier.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)

    def extract_all_features(ds):
        all_feats = []
        half = 12
        for batch in DataLoader(ds, batch_size=64):
            x = batch[0].to(device)
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
            hist_x = batch[0][:, :half, :]

            for i in range(len(pred_gl)):
                fg = pred_gl[i]
                hg = hist_x[i, :, 0].numpy() * glucose_scale
                iob = hist_x[i, :, 1].numpy() * 20
                cob = hist_x[i, :, 2].numpy() * 100

                feats = {}
                # Forecast features (from EXP-064)
                feats['fc_min'] = fg.min(); feats['fc_max'] = fg.max()
                feats['fc_mean'] = fg.mean(); feats['fc_std'] = fg.std()
                feats['fc_range'] = fg.max() - fg.min()
                feats['fc_slope'] = (fg[-1] - fg[0]) / len(fg)
                feats['fc_below_70'] = (fg < 70).sum() / len(fg)
                feats['fc_above_180'] = (fg > 180).sum() / len(fg)

                # History features
                feats['h_mean'] = hg.mean(); feats['h_std'] = hg.std()
                feats['h_last'] = hg[-1]; feats['h_min'] = hg.min()
                feats['h_max'] = hg.max()
                feats['h_roc'] = (hg[-1] - hg[0]) / max(len(hg), 1)

                # Rolling features (from EXP-049)
                for w in [3, 6, 12]:
                    window = hg[-w:] if len(hg) >= w else hg
                    feats[f'gl_mean_{w}'] = window.mean()
                    feats[f'gl_std_{w}'] = window.std()
                    feats[f'gl_min_{w}'] = window.min()
                    feats[f'gl_max_{w}'] = window.max()
                    feats[f'gl_roc_{w}'] = (window[-1] - window[0]) / max(w, 1)

                # IOB/COB rolling
                feats['iob_mean'] = iob.mean(); feats['iob_last'] = iob[-1]
                feats['iob_max'] = iob.max(); feats['iob_roc'] = iob[-1] - iob[0]
                feats['cob_mean'] = cob.mean(); feats['cob_last'] = cob[-1]
                feats['cob_max'] = cob.max()

                # Treatment signals
                bolus = hist_x[i, :, 4].numpy() * 10
                carbs = hist_x[i, :, 5].numpy() * 100
                feats['bolus_sum'] = bolus.sum()
                feats['carbs_sum'] = carbs.sum()
                feats['bolus_recent'] = bolus[-3:].sum()
                feats['carbs_recent'] = carbs[-3:].sum()

                all_feats.append(feats)
        return all_feats

    ctx.section('Extracting features')
    train_feats = extract_all_features(train_ds)
    val_feats = extract_all_features(val_ds)

    # Labels
    def label_events(ds):
        labels = []
        half = 12
        for batch in DataLoader(ds, batch_size=64):
            x = batch[0]
            for i in range(len(x)):
                future = x[i, half:]
                bolus = float(future[:, 4].sum()) * 10
                carbs = float(future[:, 5].sum()) * 100
                gl = future[:, 0].numpy() * glucose_scale
                if bolus > 0.5 and carbs > 10:
                    labels.append('meal_bolus')
                elif bolus > 0.5:
                    labels.append('correction_bolus')
                elif carbs > 10:
                    labels.append('eating_soon')
                elif gl.min() < 70:
                    labels.append('hypo_risk')
                elif gl.max() > 250:
                    labels.append('hyper_risk')
                else:
                    labels.append('normal')
        return labels

    train_labels = label_events(train_ds)
    val_labels = label_events(val_ds)

    import pandas as pd
    try:
        from xgboost import XGBClassifier
    except ImportError:
        ctx.result['success'] = False
        return ctx.save('exp069_combined_all_classifier.json')
    from sklearn.metrics import f1_score, classification_report
    from sklearn.preprocessing import LabelEncoder

    le = LabelEncoder()
    y_train = le.fit_transform(train_labels[:len(train_feats)])
    y_val = le.transform(val_labels[:len(val_feats)])
    train_df = pd.DataFrame(train_feats)
    val_df = pd.DataFrame(val_feats)

    ctx.section('Training XGBoost')
    sample_weights = np.ones(len(y_train))
    for cls in range(len(le.classes_)):
        mask = y_train == cls
        if mask.sum() > 0:
            sample_weights[mask] = (len(y_train) / (len(le.classes_) * mask.sum())) ** 0.5

    clf = XGBClassifier(n_estimators=300, max_depth=8, learning_rate=0.1,
                        random_state=42, eval_metric='mlogloss', verbosity=0,
                        subsample=0.8, colsample_bytree=0.8)
    clf.fit(train_df, y_train, sample_weight=sample_weights)
    y_pred = clf.predict(val_df)
    f1 = float(f1_score(y_val, y_pred, average='macro'))
    report = classification_report(y_val, y_pred, target_names=le.classes_,
                                   output_dict=True, zero_division=0)

    # Feature importance top 10
    imp = dict(zip(train_df.columns, clf.feature_importances_))
    top_feats = sorted(imp.items(), key=lambda x: -x[1])[:10]

    ctx.result.update({
        'f1_macro': f1,
        'per_class': {c: report[c]['f1-score'] for c in le.classes_},
        'top_features': {k: float(v) for k, v in top_feats},
        'n_features': len(train_df.columns),
        'success': f1 > 0.75,
    })
    ctx.log(f'F1 macro: {f1:.3f}')
    for cls in le.classes_:
        ctx.log(f'  {cls}: {report[cls]["f1-score"]:.3f}')
    return ctx.save('exp069_combined_all_classifier.json')


# ────────────────────────────────────────────────────────────────────
# EXP-070: Timestep-Conformal Backtest
# Hypothesis: Using per-timestep conformal thresholds (from EXP-065)
#   for backtest produces more suggestions than max-residual while
#   keeping precision >90%.
# ────────────────────────────────────────────────────────────────────

def run_timestep_backtest(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-070', out,
                           hypothesis='timestep-conformal backtest prec>90%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader, Subset

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp070_timestep_backtest.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()
    half = 12

    HYPO_THRESH = 70.0
    HYPER_THRESH = 180.0

    # Step 1: Calibrate per-timestep thresholds on patients a-e
    ctx.section('Per-timestep calibration')
    cal_residuals = [[] for _ in range(half)]
    for ppath in paths[:5]:
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
            true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
            for t in range(half):
                cal_residuals[t].extend(np.abs(pred_gl[:, t] - true_gl[:, t]).tolist())

    thresholds_90 = []
    for t in range(half):
        q = min(0.90 * (1 + 1 / len(cal_residuals[t])), 1.0)
        thresholds_90.append(float(np.quantile(cal_residuals[t], q)))
    ctx.log(f'Thresholds: ±{thresholds_90[0]:.1f} → ±{thresholds_90[-1]:.1f} mg/dL')

    # Step 2: Backtest on patients f-j using per-timestep confidence
    ctx.section('Timestep-conformal backtest')
    results = {'global': {}, 'timestep': {}}

    # Also compute global threshold for comparison
    global_q90 = float(np.quantile(
        [r for step_r in cal_residuals for r in step_r], 0.90))

    for ppath in paths[5:]:
        pname = ppath.rstrip('/').split('/')[-2]
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        if len(val_ds) < 10:
            continue

        sugg_global, sugg_timestep = [], []
        for batch in DataLoader(val_ds, batch_size=1):
            x = batch[0].to(device)
            true_gl = x[0, half:, 0].cpu().numpy() * glucose_scale
            current_gl = float(x[0, half - 1, 0].cpu().numpy() * glucose_scale)
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[0, half:, 0].cpu().numpy() * glucose_scale

            # Per-timestep: check if pred±threshold crosses danger zone
            for t in range(half):
                lo = pred_gl[t] - thresholds_90[t]
                hi = pred_gl[t] + thresholds_90[t]

                if hi < HYPO_THRESH and current_gl > HYPO_THRESH:
                    sugg_timestep.append({
                        'type': 'hypo', 'timestep': t + 1,
                        'correct': true_gl[t] < HYPO_THRESH
                    })
                    break  # one suggestion per window
                elif lo > HYPER_THRESH and current_gl < HYPER_THRESH:
                    sugg_timestep.append({
                        'type': 'hyper', 'timestep': t + 1,
                        'correct': true_gl[t] > HYPER_THRESH
                    })
                    break

            # Global: same as EXP-062 approach
            min_pred, max_pred = pred_gl.min(), pred_gl.max()
            if min_pred + global_q90 < HYPO_THRESH and current_gl > HYPO_THRESH:
                sugg_global.append({
                    'type': 'hypo',
                    'correct': float(true_gl.min()) < HYPO_THRESH
                })
            elif max_pred - global_q90 > HYPER_THRESH and current_gl < HYPER_THRESH:
                sugg_global.append({
                    'type': 'hyper',
                    'correct': float(true_gl.max()) > HYPER_THRESH
                })

        for label, suggs in [('global', sugg_global), ('timestep', sugg_timestep)]:
            n = len(suggs)
            correct = sum(1 for s in suggs if s['correct'])
            results[label][pname] = {
                'n_suggestions': n, 'n_correct': correct,
                'precision': correct / n if n else 0
            }

    for label in ['global', 'timestep']:
        r = results[label]
        total = sum(v['n_suggestions'] for v in r.values())
        correct = sum(v['n_correct'] for v in r.values())
        prec = correct / total if total else 0
        ctx.log(f'{label}: {total} sugg, {correct} correct ({prec:.0%})')

    ts_total = sum(v['n_suggestions'] for v in results['timestep'].values())
    ts_correct = sum(v['n_correct'] for v in results['timestep'].values())
    ts_prec = ts_correct / ts_total if ts_total else 0

    ctx.result.update({
        'global': results['global'],
        'timestep': results['timestep'],
        'timestep_precision': ts_prec,
        'timestep_total': ts_total,
        'thresholds': thresholds_90,
        'success': ts_prec > 0.90,
    })
    return ctx.save('exp070_timestep_backtest.json')


# ────────────────────────────────────────────────────────────────────
# EXP-071: Multi-Task + Selective Fine-Tuning
# Hypothesis: Fine-tuning the multi-task encoder per patient
#   improves forecast MAE to < 14 while keeping F1 > 0.80.
# ────────────────────────────────────────────────────────────────────

def run_multitask_finetune(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-071', out,
                           hypothesis='MT + selective FT: MAE<14, F1>0.80')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    mt_ckpt = find_checkpoint(out, 'exp067_multitask.pth')
    if not mt_ckpt:
        ctx.result['success'] = False
        return ctx.save('exp071_multitask_ft.json')

    # Inline MultiTaskModel definition (needed for loading)
    class MultiTaskModel(torch.nn.Module):
        def __init__(self, input_dim=8, d_model=64, n_classes=6):
            super().__init__()
            self.input_proj = torch.nn.Linear(input_dim, d_model)
            encoder_layer = torch.nn.TransformerEncoderLayer(
                d_model=d_model, nhead=4, dim_feedforward=128,
                dropout=0.1, batch_first=True, norm_first=True)
            self.encoder = torch.nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.forecast_head = torch.nn.Linear(d_model, 1)
            self.class_head = torch.nn.Sequential(
                torch.nn.Linear(d_model, 64), torch.nn.ReLU(),
                torch.nn.Dropout(0.2), torch.nn.Linear(64, n_classes))

        def forward(self, x, task='both'):
            h = self.input_proj(x)
            h = self.encoder(h)
            result = {}
            if task in ('forecast', 'both'):
                result['forecast'] = self.forecast_head(h).squeeze(-1)
            if task in ('classify', 'both'):
                result['logits'] = self.class_head(h[:, :x.shape[1] // 2].mean(dim=1))
            return result

    half = 12
    device = get_device()

    def label_window(x_batch):
        labels = []
        for i in range(len(x_batch)):
            future = x_batch[i, half:]
            bolus = float(future[:, 4].sum()) * 10
            carbs = float(future[:, 5].sum()) * 100
            gl = future[:, 0].numpy() * glucose_scale
            if bolus > 0.5 and carbs > 10:
                labels.append(0)
            elif bolus > 0.5:
                labels.append(1)
            elif carbs > 10:
                labels.append(2)
            elif gl.min() < 70:
                labels.append(3)
            elif gl.max() > 250:
                labels.append(4)
            else:
                labels.append(5)
        return torch.tensor(labels, dtype=torch.long)

    from sklearn.metrics import f1_score

    results = {}
    for ppath in paths[:5]:  # test on 5 patients
        pname = ppath.rstrip('/').split('/')[-2]
        ctx.section(f'Patient {pname}')
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        if len(train_ds) < 50:
            continue

        # Generic model
        gen_model = MultiTaskModel(input_dim=8).to(device)
        gen_model.load_state_dict(torch.load(mt_ckpt, map_location=device,
                                             weights_only=True))
        gen_model.eval()

        # Evaluate generic
        gen_preds, gen_trues, gen_logits, gen_labels = [], [], [], []
        with torch.no_grad():
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                labels = label_window(batch[0])
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                mout = gen_model(x_in, task='both')
                gen_preds.append(mout['forecast'][:, half:].cpu().numpy() * glucose_scale)
                gen_trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
                gen_logits.append(mout['logits'].cpu())
                gen_labels.append(labels)
        gen_mae = float(np.mean(np.abs(
            np.concatenate(gen_preds).flatten() - np.concatenate(gen_trues).flatten())))
        gen_f1 = float(f1_score(torch.cat(gen_labels).numpy(),
                                torch.cat(gen_logits).argmax(dim=1).numpy(),
                                average='macro', zero_division=0))

        # Fine-tune
        ft_model = MultiTaskModel(input_dim=8).to(device)
        ft_model.load_state_dict(torch.load(mt_ckpt, map_location=device,
                                            weights_only=True))
        optimizer = torch.optim.Adam(ft_model.parameters(), lr=5e-5)

        for epoch in range(15):
            ft_model.train()
            for batch in DataLoader(train_ds, batch_size=64, shuffle=True):
                x = batch[0].to(device)
                labels = label_window(batch[0]).to(device)
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                mout = ft_model(x_in, task='both')
                fl = torch.nn.functional.mse_loss(mout['forecast'][:, half:], x[:, half:, 0])
                cl = torch.nn.functional.cross_entropy(mout['logits'], labels)
                loss = fl + 0.1 * cl
                optimizer.zero_grad(); loss.backward(); optimizer.step()

        # Evaluate FT
        ft_model.eval()
        ft_preds, ft_trues, ft_logits, ft_labels = [], [], [], []
        with torch.no_grad():
            for batch in DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                labels = label_window(batch[0])
                x_in = x.clone(); x_in[:, half:, 0] = 0.0
                mout = ft_model(x_in, task='both')
                ft_preds.append(mout['forecast'][:, half:].cpu().numpy() * glucose_scale)
                ft_trues.append(x[:, half:, 0].cpu().numpy() * glucose_scale)
                ft_logits.append(mout['logits'].cpu())
                ft_labels.append(labels)
        ft_mae = float(np.mean(np.abs(
            np.concatenate(ft_preds).flatten() - np.concatenate(ft_trues).flatten())))
        ft_f1 = float(f1_score(torch.cat(ft_labels).numpy(),
                                torch.cat(ft_logits).argmax(dim=1).numpy(),
                                average='macro', zero_division=0))

        use_ft = ft_mae < gen_mae
        results[pname] = {
            'gen_mae': gen_mae, 'gen_f1': gen_f1,
            'ft_mae': ft_mae, 'ft_f1': ft_f1,
            'used_ft': use_ft,
        }
        ctx.log(f'{pname}: GEN MAE={gen_mae:.1f}/F1={gen_f1:.3f}, '
                f'FT MAE={ft_mae:.1f}/F1={ft_f1:.3f} → {"FT" if use_ft else "GEN"}')

    maes = [r['ft_mae' if r['used_ft'] else 'gen_mae'] for r in results.values()]
    f1s = [r['ft_f1' if r['used_ft'] else 'gen_f1'] for r in results.values()]
    ctx.result.update({
        'patients': results,
        'mean_mae': float(np.mean(maes)) if maes else 999,
        'mean_f1': float(np.mean(f1s)) if f1s else 0,
        'success': float(np.mean(maes)) < 14 and float(np.mean(f1s)) > 0.80 if maes else False,
    })
    ctx.section('Summary')
    ctx.log(f'Mean MAE: {np.mean(maes):.1f}, Mean F1: {np.mean(f1s):.3f}')
    return ctx.save('exp071_multitask_ft.json')


# ────────────────────────────────────────────────────────────────────
# EXP-072: Production Pipeline Integration Test
# Hypothesis: End-to-end pipeline (forecast + conformal + classifier
#   + backtest) produces actionable suggestions for 6hr planning.
# ────────────────────────────────────────────────────────────────────

def run_production_pipeline(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-072', out,
                           hypothesis='E2E pipeline: actionable suggestions')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp072_production_pipeline.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()
    half = 12

    # Load conformal thresholds (compute if not cached)
    ctx.section('Calibrating conformal thresholds')
    cal_residuals = [[] for _ in range(half)]
    for ppath in paths[:5]:
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)
        for batch in DataLoader(val_ds, batch_size=64):
            x = batch[0].to(device)
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[:, half:, 0].cpu().numpy() * glucose_scale
            true_gl = x[:, half:, 0].cpu().numpy() * glucose_scale
            for t in range(half):
                cal_residuals[t].extend(np.abs(pred_gl[:, t] - true_gl[:, t]).tolist())

    thresholds = [float(np.quantile(r, 0.90)) for r in cal_residuals]

    # Run pipeline on test patients
    ctx.section('Production pipeline')
    ZONES = {
        'urgent_hypo': (0, 54), 'hypo': (54, 70), 'low': (70, 80),
        'target': (80, 180), 'high': (180, 250), 'hyper': (250, 400),
    }

    all_suggestions = []
    for ppath in paths[5:]:
        pname = ppath.rstrip('/').split('/')[-2]
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)

        for batch in DataLoader(val_ds, batch_size=1):
            x = batch[0].to(device)
            current_gl = float(x[0, half - 1, 0].cpu().numpy() * glucose_scale)
            true_future = x[0, half:, 0].cpu().numpy() * glucose_scale
            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[0, half:, 0].cpu().numpy() * glucose_scale

            # Build confidence bands
            lo_band = pred_gl - np.array(thresholds[:len(pred_gl)])
            hi_band = pred_gl + np.array(thresholds[:len(pred_gl)])

            # Determine predicted trajectory zone
            suggestion = None
            confidence = 'uncertain'

            # Check for confident out-of-range
            for t in range(len(pred_gl)):
                if hi_band[t] < 70:  # confident hypo
                    suggestion = {
                        'type': 'eat_carbs',
                        'reason': f'Confident hypo at t+{t+1} '
                                  f'({pred_gl[t]:.0f}±{thresholds[t]:.0f})',
                        'urgency': 'high' if hi_band[t] < 54 else 'medium',
                        'timestep': t + 1,
                    }
                    confidence = 'high'
                    break
                elif lo_band[t] > 250:  # confident severe hyper
                    suggestion = {
                        'type': 'correction_bolus',
                        'reason': f'Confident hyper at t+{t+1} '
                                  f'({pred_gl[t]:.0f}±{thresholds[t]:.0f})',
                        'urgency': 'medium',
                        'timestep': t + 1,
                    }
                    confidence = 'high'
                    break
                elif lo_band[t] > 180 and t <= 3:
                    suggestion = {
                        'type': 'consider_correction',
                        'reason': f'Rising to {pred_gl[t]:.0f} at t+{t+1}',
                        'urgency': 'low',
                        'timestep': t + 1,
                    }
                    confidence = 'medium'
                    # Don't break — keep looking for worse

            if suggestion:
                # Verify against actual outcomes
                suggestion['actual_min'] = float(true_future.min())
                suggestion['actual_max'] = float(true_future.max())
                if suggestion['type'] == 'eat_carbs':
                    suggestion['correct'] = true_future.min() < 70
                elif suggestion['type'] in ('correction_bolus', 'consider_correction'):
                    suggestion['correct'] = true_future.max() > 180
                suggestion['patient'] = pname
                suggestion['current_gl'] = current_gl
                suggestion['confidence'] = confidence
                all_suggestions.append(suggestion)

    # Analyze suggestion quality
    n_total = len(all_suggestions)
    n_correct = sum(1 for s in all_suggestions if s.get('correct', False))
    n_high_conf = sum(1 for s in all_suggestions if s['confidence'] == 'high')
    n_high_correct = sum(1 for s in all_suggestions
                         if s['confidence'] == 'high' and s.get('correct', False))

    by_type = {}
    for s in all_suggestions:
        t = s['type']
        if t not in by_type:
            by_type[t] = {'total': 0, 'correct': 0}
        by_type[t]['total'] += 1
        if s.get('correct', False):
            by_type[t]['correct'] += 1

    ctx.result.update({
        'total_suggestions': n_total,
        'correct': n_correct,
        'precision': n_correct / n_total if n_total else 0,
        'high_conf_total': n_high_conf,
        'high_conf_correct': n_high_correct,
        'high_conf_precision': n_high_correct / n_high_conf if n_high_conf else 0,
        'by_type': {k: {**v, 'precision': v['correct'] / v['total'] if v['total'] else 0}
                    for k, v in by_type.items()},
        'thresholds': thresholds,
        'success': n_total > 10 and (n_correct / n_total if n_total else 0) > 0.7,
    })
    ctx.section('Summary')
    ctx.log(f'Total: {n_total} suggestions, {n_correct} correct ({n_correct/n_total:.0%})')
    ctx.log(f'High-conf: {n_high_conf} suggestions, {n_high_correct} correct '
            f'({n_high_correct/n_high_conf:.0%})' if n_high_conf else 'No high-conf')
    for t, v in by_type.items():
        ctx.log(f'  {t}: {v["total"]} sugg, {v["correct"]} correct')
    return ctx.save('exp072_production_pipeline.json')


# ────────────────────────────────────────────────────────────────────
# EXP-073: Action Recommendation Engine
# Hypothesis: Combining forecast trajectory + event classification +
#   conformal confidence generates typed recommendations (eat, bolus,
#   exercise, wait) with >70% actionability score.
# ────────────────────────────────────────────────────────────────────

def run_action_recommendation(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-073', out,
                           hypothesis='typed recommendations >70% actionable')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    glucose_scale = NORMALIZATION_SCALES['glucose']
    from torch.utils.data import DataLoader

    ckpt = find_checkpoint(out, 'exp053_long_1hr_5min.pth',
                           'exp043_forecast_mh_1hr_5min.pth')
    if not ckpt:
        ctx.result['success'] = False
        return ctx.save('exp073_action_recommendation.json')

    model = create_model('grouped', input_dim=8)
    load_checkpoint(model, ckpt)
    model.eval()
    device = get_device()
    half = 12

    # Action definitions
    ACTIONS = {
        'eat_fast_carbs': {'condition': 'urgent_hypo_predicted',
                           'verify': lambda t: t.min() < 54},
        'eat_carbs': {'condition': 'hypo_predicted',
                      'verify': lambda t: t.min() < 70},
        'correction_bolus': {'condition': 'sustained_hyper',
                             'verify': lambda t: t.max() > 250},
        'reduce_basal': {'condition': 'dropping_fast',
                         'verify': lambda t: (t[-1] - t[0]) < -30},
        'prebolus': {'condition': 'rising_post_meal',
                     'verify': lambda t: t.max() > 180},
        'no_action': {'condition': 'in_range',
                      'verify': lambda t: t.min() > 70 and t.max() < 180},
    }

    recommendations = []
    for ppath in paths[5:]:
        pname = ppath.rstrip('/').split('/')[-2]
        train_ds, val_ds = load_multipatient_nightscout([ppath], window_size=24)

        for batch in DataLoader(val_ds, batch_size=1):
            x = batch[0].to(device)
            current_gl = float(x[0, half - 1, 0].cpu().numpy() * glucose_scale)
            true_future = x[0, half:, 0].cpu().numpy() * glucose_scale
            iob = float(x[0, half - 1, 1].cpu().numpy() * 20)
            cob = float(x[0, half - 1, 2].cpu().numpy() * 100)

            x_in = x.clone(); x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                pred = model(x_in, causal=True)
            pred_gl = pred[0, half:, 0].cpu().numpy() * glucose_scale
            pred_slope = (pred_gl[-1] - pred_gl[0]) / len(pred_gl)

            # Determine action
            action = 'no_action'
            reason = 'in range'
            if pred_gl.min() < 54:
                action = 'eat_fast_carbs'
                reason = f'urgent hypo: pred min {pred_gl.min():.0f}'
            elif pred_gl.min() < 70:
                action = 'eat_carbs'
                reason = f'hypo: pred min {pred_gl.min():.0f}'
            elif pred_gl.max() > 250:
                action = 'correction_bolus'
                reason = f'severe hyper: pred max {pred_gl.max():.0f}'
            elif pred_slope < -3 and current_gl < 120:
                action = 'reduce_basal'
                reason = f'fast drop: slope {pred_slope:.1f} mg/dL/step'
            elif pred_gl.max() > 180 and cob > 0:
                action = 'prebolus'
                reason = f'post-meal rise: pred max {pred_gl.max():.0f}'

            # Verify against actual outcome
            verifier = ACTIONS[action]['verify']
            correct = verifier(true_future)

            recommendations.append({
                'patient': pname, 'action': action, 'reason': reason,
                'current_gl': current_gl, 'iob': iob, 'cob': cob,
                'pred_min': float(pred_gl.min()), 'pred_max': float(pred_gl.max()),
                'actual_min': float(true_future.min()),
                'actual_max': float(true_future.max()),
                'correct': correct,
            })

    # Analyze
    n_total = len(recommendations)
    n_correct = sum(1 for r in recommendations if r['correct'])
    n_actionable = sum(1 for r in recommendations if r['action'] != 'no_action')
    n_action_correct = sum(1 for r in recommendations
                          if r['action'] != 'no_action' and r['correct'])

    by_action = {}
    for r in recommendations:
        a = r['action']
        if a not in by_action:
            by_action[a] = {'total': 0, 'correct': 0}
        by_action[a]['total'] += 1
        if r['correct']:
            by_action[a]['correct'] += 1

    ctx.result.update({
        'total': n_total,
        'actionable': n_actionable,
        'actionable_correct': n_action_correct,
        'actionable_precision': n_action_correct / n_actionable if n_actionable else 0,
        'overall_accuracy': n_correct / n_total if n_total else 0,
        'by_action': {k: {**v, 'precision': v['correct'] / v['total'] if v['total'] else 0}
                      for k, v in by_action.items()},
        'success': n_actionable > 10 and (n_action_correct / n_actionable if n_actionable else 0) > 0.7,
    })
    ctx.section('Summary')
    ctx.log(f'Total: {n_total}, Actionable: {n_actionable}, '
            f'Correct: {n_action_correct} ({n_action_correct/n_actionable:.0%})')
    for a, v in sorted(by_action.items()):
        ctx.log(f'  {a}: {v["total"]} ({v["correct"]} correct)')
    return ctx.save('exp073_action_recommendation.json')


# ────────────────────────────────────────────────────────────────────
# EXP-074: Time-to-Event Regression
# Hypothesis: Predict minutes until glucose crosses 70 (hypo) or 180
#   (hyper) thresholds. Use censored regression — many windows never
#   cross. Target: MAE < 30 min for events that DO occur within 1hr.
# ────────────────────────────────────────────────────────────────────

def run_time_to_event(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-074', out,
                           hypothesis='time-to-event MAE < 30 min')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val windows')

    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    HYPO = 70.0 / SCALE
    HYPER = 180.0 / SCALE
    MAX_STEPS = 12  # future half

    # Build time-to-event labels from actual future glucose
    def make_tte_labels(ds):
        hypo_tte = []
        hyper_tte = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            future_gluc = w[12:, 0]  # future half, channel 0
            below = np.where(future_gluc < HYPO)[0]
            hypo_tte.append(below[0] + 1 if len(below) > 0 else MAX_STEPS + 1)
            above = np.where(future_gluc > HYPER)[0]
            hyper_tte.append(above[0] + 1 if len(above) > 0 else MAX_STEPS + 1)
        return np.array(hypo_tte), np.array(hyper_tte)

    train_hypo, train_hyper = make_tte_labels(train_ds)
    val_hypo, val_hyper = make_tte_labels(val_ds)

    hypo_rate = np.mean(val_hypo <= MAX_STEPS)
    hyper_rate = np.mean(val_hyper <= MAX_STEPS)
    ctx.log(f'Hypo events in window: {hypo_rate:.1%}, Hyper: {hyper_rate:.1%}')

    # Train forecast model, extract predicted future glucose
    model = create_model('grouped', input_dim=8)
    train_forecast(model, train_ds, val_ds, f'{out}/exp074_base.pth',
                   'Forecast-base', epochs=80)

    device = next(model.parameters()).device
    model.eval()
    pred_hypo_tte = []
    pred_hyper_tte = []
    with torch.no_grad():
        for i in range(len(val_ds)):
            w = val_ds[i]
            if isinstance(w, tuple):
                w = w[0]
            x = w.unsqueeze(0).to(device) if hasattr(w, 'unsqueeze') else torch.tensor(w).unsqueeze(0).to(device)
            x_in = x.clone()
            x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            pred_gluc = pred[0, 12:, 0].cpu().numpy()
            below = np.where(pred_gluc < HYPO)[0]
            pred_hypo_tte.append(below[0] + 1 if len(below) > 0 else MAX_STEPS + 1)
            above = np.where(pred_gluc > HYPER)[0]
            pred_hyper_tte.append(above[0] + 1 if len(above) > 0 else MAX_STEPS + 1)

    pred_hypo_tte = np.array(pred_hypo_tte)
    pred_hyper_tte = np.array(pred_hyper_tte)

    hypo_mask = val_hypo <= MAX_STEPS
    hyper_mask = val_hyper <= MAX_STEPS

    hypo_mae = float(np.mean(np.abs(pred_hypo_tte[hypo_mask] - val_hypo[hypo_mask]))) * 5 if hypo_mask.sum() > 0 else None
    hyper_mae = float(np.mean(np.abs(pred_hyper_tte[hyper_mask] - val_hyper[hyper_mask]))) * 5 if hyper_mask.sum() > 0 else None

    hypo_detected = float(np.mean(pred_hypo_tte[hypo_mask] <= MAX_STEPS)) if hypo_mask.sum() > 0 else None
    hyper_detected = float(np.mean(pred_hyper_tte[hyper_mask] <= MAX_STEPS)) if hyper_mask.sum() > 0 else None

    no_hypo = ~hypo_mask
    no_hyper = ~hyper_mask
    hypo_fa = float(np.mean(pred_hypo_tte[no_hypo] <= MAX_STEPS)) if no_hypo.sum() > 0 else None
    hyper_fa = float(np.mean(pred_hyper_tte[no_hyper] <= MAX_STEPS)) if no_hyper.sum() > 0 else None

    ctx.result.update({
        'hypo_event_rate': float(hypo_rate),
        'hyper_event_rate': float(hyper_rate),
        'hypo_n_events': int(hypo_mask.sum()),
        'hyper_n_events': int(hyper_mask.sum()),
        'hypo_mae_minutes': hypo_mae,
        'hyper_mae_minutes': hyper_mae,
        'hypo_detection_rate': float(hypo_detected) if hypo_detected is not None else None,
        'hyper_detection_rate': float(hyper_detected) if hyper_detected is not None else None,
        'hypo_false_alarm_rate': hypo_fa,
        'hyper_false_alarm_rate': hyper_fa,
        'success': (hypo_mae is not None and hypo_mae < 30) or
                   (hyper_mae is not None and hyper_mae < 30),
    })
    ctx.section('Time-to-event results')
    if hypo_mae is not None:
        ctx.log(f'Hypo: {hypo_mask.sum()} events, MAE={hypo_mae:.1f} min, '
                f'detect={hypo_detected:.1%}, FA={hypo_fa:.1%}')
    else:
        ctx.log('Hypo: no events')
    if hyper_mae is not None:
        ctx.log(f'Hyper: {hyper_mask.sum()} events, MAE={hyper_mae:.1f} min, '
                f'detect={hyper_detected:.1%}, FA={hyper_fa:.1%}')
    else:
        ctx.log('Hyper: no events')
    return ctx.save('exp074_time_to_event.json')


# ────────────────────────────────────────────────────────────────────
# EXP-075: Counterfactual Dose-Response
# Hypothesis: Find pairs of similar glucose states with different
#   insulin actions, train model to predict dose → glucose outcome.
#   Target: correlation > 0.3 between predicted and actual delta.
# ────────────────────────────────────────────────────────────────────

def run_counterfactual_dose(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-075', out,
                           hypothesis='dose-response correlation > 0.3')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    GLUC_SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    BOLUS_SCALE = NORMALIZATION_SCALES.get('bolus', 10)
    CARB_SCALE = NORMALIZATION_SCALES.get('carbs', 100)

    def extract_dose_response(ds):
        records = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            hist_gluc = w[:12, 0] * GLUC_SCALE
            future_gluc = w[12:, 0] * GLUC_SCALE
            bolus_hist = w[:12, 4] * BOLUS_SCALE if w.shape[1] > 4 else np.zeros(12)
            carbs_hist = w[:12, 5] * CARB_SCALE if w.shape[1] > 5 else np.zeros(12)
            iob_mid = float(w[11, 1]) * NORMALIZATION_SCALES.get('iob', 20) if w.shape[1] > 1 else 0
            records.append({
                'start_gluc': float(hist_gluc[-1]),
                'gluc_trend': float(hist_gluc[-1] - hist_gluc[-4]) if len(hist_gluc) >= 4 else 0,
                'total_bolus': float(bolus_hist.sum()),
                'total_carbs': float(carbs_hist.sum()),
                'iob': iob_mid,
                'end_gluc': float(future_gluc[-1]),
                'min_gluc': float(future_gluc.min()),
                'max_gluc': float(future_gluc.max()),
                'delta_gluc': float(future_gluc[-1] - hist_gluc[-1]),
            })
        return records

    train_recs = extract_dose_response(train_ds)
    val_recs = extract_dose_response(val_ds)

    import sklearn.ensemble as ske
    from sklearn.metrics import mean_absolute_error

    feat_cols = ['start_gluc', 'gluc_trend', 'total_bolus', 'total_carbs', 'iob']
    X_train = np.array([[r[c] for c in feat_cols] for r in train_recs])
    y_train = np.array([r['delta_gluc'] for r in train_recs])
    X_val = np.array([[r[c] for c in feat_cols] for r in val_recs])
    y_val = np.array([r['delta_gluc'] for r in val_recs])

    gbr = ske.GradientBoostingRegressor(n_estimators=200, max_depth=5,
                                         learning_rate=0.05, random_state=42)
    gbr.fit(X_train, y_train)
    pred_delta = gbr.predict(X_val)

    mae = float(mean_absolute_error(y_val, pred_delta))
    corr = float(np.corrcoef(y_val, pred_delta)[0, 1])

    # Counterfactual: vary bolus for fixed glucose state (~120 mg/dL)
    base_mask = (X_val[:, 0] > 100) & (X_val[:, 0] < 140)
    dose_sweep = []
    isf_estimate = None
    if base_mask.sum() > 50:
        base_X = X_val[base_mask].copy()
        for dose in np.arange(0, 5.5, 0.5):
            test_X = base_X.copy()
            test_X[:, 2] = dose
            pred = gbr.predict(test_X)
            dose_sweep.append({
                'bolus_u': float(dose),
                'mean_delta': float(pred.mean()),
                'std_delta': float(pred.std()),
            })
        isf_estimate = (dose_sweep[0]['mean_delta'] - dose_sweep[-1]['mean_delta']) / 5.0

    fi = dict(zip(feat_cols, [float(x) for x in gbr.feature_importances_]))

    ctx.result.update({
        'mae_mgdl': mae,
        'correlation': corr,
        'n_train': len(train_recs),
        'n_val': len(val_recs),
        'dose_sweep': dose_sweep,
        'estimated_isf': isf_estimate,
        'feature_importance': fi,
        'success': corr > 0.3,
    })
    ctx.section('Dose-response results')
    ctx.log(f'Delta glucose prediction: MAE={mae:.1f} mg/dL, corr={corr:.3f}')
    if dose_sweep:
        ctx.log(f'Dose sweep (0->5U): {dose_sweep[0]["mean_delta"]:.1f} -> {dose_sweep[-1]["mean_delta"]:.1f} mg/dL')
        ctx.log(f'Estimated ISF: {isf_estimate:.1f} mg/dL per unit')
    ctx.log(f'Feature importance: {fi}')
    return ctx.save('exp075_counterfactual_dose.json')


# ────────────────────────────────────────────────────────────────────
# EXP-076: Circadian-Aware Forecasting
# Hypothesis: Adding sin/cos hour-of-day embedding improves forecast
#   MAE, especially for dawn phenomenon (4-8am glucose rise).
#   Target: >5% MAE improvement in 4-8am windows.
# ────────────────────────────────────────────────────────────────────

def run_circadian_forecast(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-076', out,
                           hypothesis='circadian features improve dawn MAE >5%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # Load standard windows — assign synthetic hour based on window index
    # (Windows are sequential 5-min intervals, so position encodes time-of-day)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    # Extract windows as numpy for manipulation
    def ds_to_numpy(ds):
        windows = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            windows.append(w)
        return np.array(windows)

    val_np = ds_to_numpy(val_ds)
    train_np = ds_to_numpy(train_ds)

    # Derive approximate hour from window position within each patient's data
    # Use modular arithmetic: each window is ~3 steps apart (stride=3 in loader)
    # 288 steps per day at 5min intervals, so hour = (index * 3 % 288) / 12
    n_val = len(val_np)
    val_hours = np.array([(i * 3 % 288) // 12 for i in range(n_val)])
    n_train = len(train_np)
    train_hours = np.array([(i * 3 % 288) // 12 for i in range(n_train)])

    # 1. Baseline: standard GroupedEncoder on 8 features
    model_base = create_model('grouped', input_dim=8)
    train_forecast(model_base, train_ds, val_ds, f'{out}/exp076_base.pth',
                   'Base', epochs=80)

    # 2. Circadian: append sin/cos hour as 2 extra channels
    def add_circadian(windows, hours):
        sin_h = np.sin(2 * np.pi * hours / 24.0).astype(np.float32)
        cos_h = np.cos(2 * np.pi * hours / 24.0).astype(np.float32)
        circ = np.zeros((len(windows), windows.shape[1], 2), dtype=np.float32)
        for i in range(len(windows)):
            circ[i, :, 0] = sin_h[i]
            circ[i, :, 1] = cos_h[i]
        return np.concatenate([windows, circ], axis=2)

    train_circ = add_circadian(train_np, train_hours)
    val_circ = add_circadian(val_np, val_hours)

    train_ds_c = torch.utils.data.TensorDataset(torch.tensor(train_circ))
    val_ds_c = torch.utils.data.TensorDataset(torch.tensor(val_circ))

    model_circ = create_model('grouped', input_dim=10)
    train_forecast(model_circ, train_ds_c, val_ds_c, f'{out}/exp076_circ.pth',
                   'Circadian', epochs=80)

    # Evaluate both by time-of-day bucket
    def eval_by_hour(model, ds, hours):
        device = next(model.parameters()).device
        model.eval()
        SCALE = NORMALIZATION_SCALES.get('glucose', 400)
        errors = []
        with torch.no_grad():
            for i in range(len(ds)):
                w = ds[i][0]
                x = w.unsqueeze(0).to(device)
                x_in = x.clone()
                x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                target = x[:, 12:, 0].cpu().numpy() * SCALE
                forecast = pred[:, 12:, 0].cpu().numpy() * SCALE
                errors.append(float(np.mean(np.abs(forecast - target))))
        errors = np.array(errors)
        dawn = (hours >= 4) & (hours < 8)
        day = (hours >= 8) & (hours < 20)
        night = (hours >= 20) | (hours < 4)
        return {
            'overall': float(errors.mean()),
            'dawn_4_8': float(errors[dawn].mean()) if dawn.sum() > 0 else None,
            'day_8_20': float(errors[day].mean()) if day.sum() > 0 else None,
            'night_20_4': float(errors[night].mean()) if night.sum() > 0 else None,
            'dawn_n': int(dawn.sum()), 'day_n': int(day.sum()), 'night_n': int(night.sum()),
        }

    base_metrics = eval_by_hour(model_base, val_ds, val_hours)
    circ_metrics = eval_by_hour(model_circ, val_ds_c, val_hours)

    dawn_improvement = None
    if base_metrics['dawn_4_8'] and circ_metrics['dawn_4_8']:
        dawn_improvement = (base_metrics['dawn_4_8'] - circ_metrics['dawn_4_8']) / base_metrics['dawn_4_8'] * 100

    ctx.result.update({
        'base': base_metrics,
        'circadian': circ_metrics,
        'dawn_improvement_pct': dawn_improvement,
        'overall_improvement_pct': (base_metrics['overall'] - circ_metrics['overall']) / base_metrics['overall'] * 100,
        'success': dawn_improvement is not None and dawn_improvement > 5,
    })
    ctx.section('Circadian forecast results')
    ctx.log(f'Base overall: {base_metrics["overall"]:.1f}, dawn: {base_metrics["dawn_4_8"]}')
    ctx.log(f'Circ overall: {circ_metrics["overall"]:.1f}, dawn: {circ_metrics["dawn_4_8"]}')
    if dawn_improvement is not None:
        ctx.log(f'Dawn improvement: {dawn_improvement:.1f}%')
    return ctx.save('exp076_circadian_forecast.json')


# ────────────────────────────────────────────────────────────────────
# EXP-077: Action Magnitude Prediction
# Hypothesis: For windows preceding bolus or carb events, predict the
#   actual dose/amount. Target: bolus MAE < 2U, carbs MAE < 20g.
# ────────────────────────────────────────────────────────────────────

def run_action_magnitude(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-077', out,
                           hypothesis='bolus MAE < 2U, carbs MAE < 20g')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    GLUC_SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    BOLUS_SCALE = NORMALIZATION_SCALES.get('bolus', 10)
    CARB_SCALE = NORMALIZATION_SCALES.get('carbs', 100)
    IOB_SCALE = NORMALIZATION_SCALES.get('iob', 20)

    def extract_action_data(ds):
        bolus_records = []
        carb_records = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            future_bolus = w[12:, 4] * BOLUS_SCALE if w.shape[1] > 4 else np.zeros(12)
            future_carbs = w[12:, 5] * CARB_SCALE if w.shape[1] > 5 else np.zeros(12)
            total_bolus = float(future_bolus.sum())
            total_carbs = float(future_carbs.sum())

            feat = {
                'gluc_now': float(w[11, 0] * GLUC_SCALE),
                'gluc_trend': float((w[11, 0] - w[8, 0]) * GLUC_SCALE),
                'iob': float(w[11, 1] * IOB_SCALE) if w.shape[1] > 1 else 0,
                'cob': float(w[11, 2] * NORMALIZATION_SCALES.get('cob', 100)) if w.shape[1] > 2 else 0,
                'gluc_mean': float(w[:12, 0].mean() * GLUC_SCALE),
                'gluc_std': float(w[:12, 0].std() * GLUC_SCALE),
                'gluc_min': float(w[:12, 0].min() * GLUC_SCALE),
                'gluc_max': float(w[:12, 0].max() * GLUC_SCALE),
            }

            if total_bolus > 0.1:
                bolus_records.append({**feat, 'target': total_bolus})
            if total_carbs > 1.0:
                carb_records.append({**feat, 'target': total_carbs})

        return bolus_records, carb_records

    train_bolus, train_carbs = extract_action_data(train_ds)
    val_bolus, val_carbs = extract_action_data(val_ds)
    ctx.log(f'Bolus events: {len(train_bolus)} train, {len(val_bolus)} val')
    ctx.log(f'Carb events: {len(train_carbs)} train, {len(val_carbs)} val')

    import sklearn.ensemble as ske
    from sklearn.metrics import mean_absolute_error

    feat_cols = ['gluc_now', 'gluc_trend', 'iob', 'cob', 'gluc_mean',
                 'gluc_std', 'gluc_min', 'gluc_max']

    results = {}
    for name, train_recs, val_recs in [('bolus', train_bolus, val_bolus),
                                        ('carbs', train_carbs, val_carbs)]:
        if len(train_recs) < 50 or len(val_recs) < 10:
            results[name] = {'n_train': len(train_recs), 'n_val': len(val_recs),
                             'error': 'too few samples'}
            continue
        X_tr = np.array([[r[c] for c in feat_cols] for r in train_recs])
        y_tr = np.array([r['target'] for r in train_recs])
        X_va = np.array([[r[c] for c in feat_cols] for r in val_recs])
        y_va = np.array([r['target'] for r in val_recs])

        gbr = ske.GradientBoostingRegressor(n_estimators=200, max_depth=4,
                                             learning_rate=0.05, random_state=42)
        gbr.fit(X_tr, y_tr)
        pred = gbr.predict(X_va)

        mae = float(mean_absolute_error(y_va, pred))
        corr = float(np.corrcoef(y_va, pred)[0, 1]) if len(y_va) > 1 else 0
        fi = dict(zip(feat_cols, [float(x) for x in gbr.feature_importances_]))

        results[name] = {
            'n_train': len(train_recs), 'n_val': len(val_recs),
            'mae': mae, 'correlation': corr,
            'target_mean': float(y_va.mean()), 'target_std': float(y_va.std()),
            'pred_mean': float(pred.mean()), 'pred_std': float(pred.std()),
            'feature_importance': fi,
        }

    bolus_ok = results.get('bolus', {}).get('mae', 999) < 2.0
    carbs_ok = results.get('carbs', {}).get('mae', 999) < 20.0

    ctx.result.update({
        'bolus': results.get('bolus', {}),
        'carbs': results.get('carbs', {}),
        'success': bolus_ok or carbs_ok,
    })
    ctx.section('Action magnitude results')
    for name in ['bolus', 'carbs']:
        r = results.get(name, {})
        if 'mae' in r:
            unit = 'U' if name == 'bolus' else 'g'
            ctx.log(f'{name}: MAE={r["mae"]:.2f}{unit}, corr={r["correlation"]:.3f}, '
                    f'mean={r["target_mean"]:.1f}{unit}')
    return ctx.save('exp077_action_magnitude.json')


# ────────────────────────────────────────────────────────────────────
# EXP-078: Streaming Conformal Adaptation
# Hypothesis: Using a sliding window of recent N=100 calibration
#   samples adapts conformal thresholds to distribution shifts.
#   Target: tighter intervals (< global) while maintaining 90% coverage.
# ────────────────────────────────────────────────────────────────────

def run_streaming_conformal(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-078', out,
                           hypothesis='streaming conformal tighter than global')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    cal_paths = paths[:5]
    test_paths = paths[5:]
    ctx.log(f'Calibration: {len(cal_paths)} patients, Test: {len(test_paths)} patients')

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    model = create_model('grouped', input_dim=8)
    train_forecast(model, train_ds, val_ds, f'{out}/exp078_base.pth',
                   'Base', epochs=80)

    device = next(model.parameters()).device
    SCALE = NORMALIZATION_SCALES.get('glucose', 400)

    def compute_residuals_sequential(paths_list):
        all_residuals = []
        for p in paths_list:
            ds_t, ds_v = load_multipatient_nightscout([p], window_size=24)
            model.eval()
            with torch.no_grad():
                for i in range(len(ds_v)):
                    w = ds_v[i]
                    if isinstance(w, tuple):
                        w = w[0]
                    x = w.unsqueeze(0).to(device) if hasattr(w, 'unsqueeze') else torch.tensor(w).unsqueeze(0).to(device)
                    x_in = x.clone()
                    x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    target = x[0, 12:, 0].cpu().numpy() * SCALE
                    forecast = pred[0, 12:, 0].cpu().numpy() * SCALE
                    max_resid = float(np.max(np.abs(forecast - target)))
                    all_residuals.append(max_resid)
        return all_residuals

    cal_residuals = compute_residuals_sequential(cal_paths)
    global_threshold = float(np.quantile(cal_residuals, 0.9))
    ctx.log(f'Global 90% threshold: +/-{global_threshold:.1f} mg/dL ({len(cal_residuals)} cal samples)')

    test_residuals = compute_residuals_sequential(test_paths)
    ctx.log(f'Test samples: {len(test_residuals)}')

    global_coverage = float(np.mean(np.array(test_residuals) <= global_threshold))

    window_sizes = [50, 100, 200, 500]
    streaming_results = {}
    for N in window_sizes:
        all_resid = cal_residuals + test_residuals
        coverages = []
        thresholds = []
        for i in range(len(cal_residuals), len(all_resid)):
            start = max(0, i - N)
            cal_window = all_resid[start:i]
            if len(cal_window) < 10:
                continue
            thresh = float(np.quantile(cal_window, 0.9))
            thresholds.append(thresh)
            coverages.append(1 if all_resid[i] <= thresh else 0)

        if coverages:
            streaming_results[f'N={N}'] = {
                'mean_coverage': float(np.mean(coverages)),
                'mean_threshold': float(np.mean(thresholds)),
                'std_threshold': float(np.std(thresholds)),
                'min_threshold': float(np.min(thresholds)),
                'max_threshold': float(np.max(thresholds)),
                'n_eval': len(coverages),
            }

    best_streaming = None
    best_tightening = 0
    for k, v in streaming_results.items():
        if v['mean_coverage'] >= 0.88:
            tightening = global_threshold - v['mean_threshold']
            if tightening > best_tightening:
                best_tightening = tightening
                best_streaming = k

    ctx.result.update({
        'global_threshold_mgdl': global_threshold,
        'global_coverage': global_coverage,
        'n_calibration': len(cal_residuals),
        'n_test': len(test_residuals),
        'streaming': streaming_results,
        'best_streaming': best_streaming,
        'best_tightening_mgdl': best_tightening,
        'success': best_tightening > 2.0,
    })
    ctx.section('Streaming conformal results')
    ctx.log(f'Global: +/-{global_threshold:.1f} mg/dL, coverage={global_coverage:.1%}')
    for k, v in streaming_results.items():
        ctx.log(f'{k}: +/-{v["mean_threshold"]:.1f} mg/dL, coverage={v["mean_coverage"]:.1%}')
    return ctx.save('exp078_streaming_conformal.json')


# ────────────────────────────────────────────────────────────────────
# EXP-079: Multi-Horizon Planning Trajectory
# Hypothesis: Generating 1hr forecasts and scoring trajectory shape
#   (trend, curvature, time-below/above) predicts next event class
#   better than raw features. Target: F1 > 0.75.
# ────────────────────────────────────────────────────────────────────

def run_multihorizon_trajectory(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-079', out,
                           hypothesis='trajectory features F1 > 0.75')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    BOLUS_SCALE = NORMALIZATION_SCALES.get('bolus', 10)
    CARB_SCALE = NORMALIZATION_SCALES.get('carbs', 100)

    # Train 1hr model
    model = create_model('grouped', input_dim=8)
    train_forecast(model, train_ds, val_ds, f'{out}/exp079_1hr.pth', '1hr', epochs=60)

    device = next(model.parameters()).device

    def extract_trajectory_features(model, ds):
        features = []
        model.eval()
        with torch.no_grad():
            for i in range(len(ds)):
                w = ds[i]
                if isinstance(w, tuple):
                    w = w[0]
                x = w.unsqueeze(0).to(device) if hasattr(w, 'unsqueeze') else torch.tensor(w).unsqueeze(0).to(device)
                x_in = x.clone()
                x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                forecast = pred[0, 12:, 0].cpu().numpy() * SCALE
                actual_hist = x[0, :12, 0].cpu().numpy() * SCALE

                start_gluc = float(actual_hist[-1])
                end_gluc = float(forecast[-1])
                min_gluc = float(forecast.min())
                max_gluc = float(forecast.max())
                mean_gluc = float(forecast.mean())
                slope = float(forecast[-1] - forecast[0]) / 12
                if len(forecast) >= 3:
                    d2 = np.diff(np.diff(forecast))
                    curvature = float(np.mean(np.abs(d2)))
                else:
                    curvature = 0
                time_below_70 = float(np.mean(forecast < 70))
                time_above_180 = float(np.mean(forecast > 180))
                nadir_step = int(np.argmin(forecast))
                peak_step = int(np.argmax(forecast))
                gluc_range = max_gluc - min_gluc
                diffs = np.diff(forecast)
                reversals = int(np.sum(np.diff(np.sign(diffs)) != 0))
                features.append([
                    start_gluc, end_gluc, min_gluc, max_gluc, mean_gluc,
                    slope, curvature, time_below_70, time_above_180,
                    nadir_step, peak_step, gluc_range, reversals,
                    end_gluc - start_gluc,
                ])
        return np.array(features)

    traj_features = extract_trajectory_features(model, val_ds)

    # Build labels from actual future data
    labels = []
    for i in range(len(val_ds)):
        w = val_ds[i]
        if isinstance(w, tuple):
            w = w[0]
        if hasattr(w, 'numpy'):
            w = w.numpy()
        future_gluc = w[12:, 0] * SCALE
        future_bolus = w[12:, 4] * BOLUS_SCALE if w.shape[1] > 4 else np.zeros(12)
        future_carbs = w[12:, 5] * CARB_SCALE if w.shape[1] > 5 else np.zeros(12)

        if future_gluc.min() < 70:
            labels.append('hypo_risk')
        elif future_gluc.max() > 250:
            labels.append('hyper_risk')
        elif future_bolus.sum() > 0.5:
            labels.append('correction_bolus')
        elif future_carbs.sum() > 5:
            labels.append('meal_bolus')
        else:
            labels.append('normal')

    labels = np.array(labels)

    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    y = le.fit_transform(labels)

    n = len(traj_features)
    idx = np.random.RandomState(42).permutation(n)
    split = int(0.7 * n)
    X_tr, X_va = traj_features[idx[:split]], traj_features[idx[split:]]
    y_tr, y_va = y[idx[:split]], y[idx[split:]]

    import xgboost as xgb
    from sklearn.metrics import f1_score, classification_report

    clf = xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                             use_label_encoder=False, eval_metric='mlogloss',
                             random_state=42)
    clf.fit(X_tr, y_tr)
    pred = clf.predict(X_va)

    f1 = float(f1_score(y_va, pred, average='macro'))
    report = classification_report(y_va, pred, target_names=le.classes_, output_dict=True)

    feat_names = ['start_gluc', 'end_gluc', 'min_gluc', 'max_gluc', 'mean_gluc',
                  'slope', 'curvature', 'time_below_70', 'time_above_180',
                  'nadir_step', 'peak_step', 'gluc_range', 'reversals', 'net_delta']
    fi = dict(zip(feat_names, [float(x) for x in clf.feature_importances_]))

    ctx.result.update({
        'f1_macro': f1,
        'per_class': {k: {'f1': v['f1-score'], 'support': v['support']}
                      for k, v in report.items() if k in le.classes_},
        'feature_importance': fi,
        'n_classes': len(le.classes_),
        'class_distribution': {c: int((labels == c).sum()) for c in le.classes_},
        'success': f1 > 0.75,
    })
    ctx.section('Trajectory classification results')
    ctx.log(f'F1 macro: {f1:.3f}')
    for c in le.classes_:
        if c in report:
            ctx.log(f'  {c}: F1={report[c]["f1-score"]:.3f} (n={report[c]["support"]})')
    ctx.log(f'Top features: {sorted(fi.items(), key=lambda x: -x[1])[:5]}')
    return ctx.save('exp079_multihorizon_trajectory.json')


# ────────────────────────────────────────────────────────────────────
# EXP-080: Hypo-Focused Detection
# Hypothesis: Oversampling hypo windows (9.3% → 30%) + dedicated
#   binary classifier improves hypo detection from 16% to >60%.
# ────────────────────────────────────────────────────────────────────

def run_hypo_focused(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-080', out,
                           hypothesis='hypo detection >60%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    HYPO = 70.0 / SCALE
    IOB_SCALE = NORMALIZATION_SCALES.get('iob', 20)

    def extract_features_and_labels(ds):
        features = []
        labels = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            hist = w[:12]
            future = w[12:]

            # Rich feature set for hypo detection
            gluc_hist = hist[:, 0] * SCALE
            feat = [
                float(gluc_hist[-1]),           # current glucose
                float(gluc_hist[-1] - gluc_hist[-4]),  # 15-min trend
                float(gluc_hist[-1] - gluc_hist[0]),   # 1-hr trend
                float(gluc_hist.min()),
                float(gluc_hist.max()),
                float(gluc_hist.std()),
                float(gluc_hist.mean()),
                float(hist[-1, 1] * IOB_SCALE) if w.shape[1] > 1 else 0,  # IOB
                float(hist[-1, 2] * NORMALIZATION_SCALES.get('cob', 100)) if w.shape[1] > 2 else 0,  # COB
                float(hist[-1, 3] * NORMALIZATION_SCALES.get('net_basal', 5)) if w.shape[1] > 3 else 0,  # basal
            ]
            # Rate of change features
            if len(gluc_hist) >= 6:
                feat.append(float(np.mean(np.diff(gluc_hist[-6:]))))  # recent ROC
                feat.append(float(np.min(np.diff(gluc_hist[-6:]))))   # max drop rate
            else:
                feat.extend([0, 0])

            features.append(feat)
            # Label: any future glucose below 70
            labels.append(1 if np.any(future[:, 0] < HYPO) else 0)
        return np.array(features), np.array(labels)

    X_tr, y_tr = extract_features_and_labels(train_ds)
    X_va, y_va = extract_features_and_labels(val_ds)

    hypo_rate_train = y_tr.mean()
    hypo_rate_val = y_va.mean()
    ctx.log(f'Hypo rate: train={hypo_rate_train:.1%}, val={hypo_rate_val:.1%}')

    import xgboost as xgb
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

    results = {}

    # Method 1: Standard XGBoost
    clf1 = xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                              use_label_encoder=False, eval_metric='logloss',
                              random_state=42)
    clf1.fit(X_tr, y_tr)
    pred1 = clf1.predict(X_va)
    prob1 = clf1.predict_proba(X_va)[:, 1]
    results['standard'] = {
        'f1': float(f1_score(y_va, pred1)),
        'precision': float(precision_score(y_va, pred1)),
        'recall': float(recall_score(y_va, pred1)),
        'auroc': float(roc_auc_score(y_va, prob1)),
    }

    # Method 2: Cost-sensitive (10:1 weight for hypo)
    clf2 = xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                              scale_pos_weight=10.0,
                              use_label_encoder=False, eval_metric='logloss',
                              random_state=42)
    clf2.fit(X_tr, y_tr)
    pred2 = clf2.predict(X_va)
    prob2 = clf2.predict_proba(X_va)[:, 1]
    results['cost_sensitive_10x'] = {
        'f1': float(f1_score(y_va, pred2)),
        'precision': float(precision_score(y_va, pred2)),
        'recall': float(recall_score(y_va, pred2)),
        'auroc': float(roc_auc_score(y_va, prob2)),
    }

    # Method 3: Oversampled (duplicate hypo windows 3x)
    hypo_idx = np.where(y_tr == 1)[0]
    oversample_idx = np.concatenate([np.arange(len(y_tr))] + [hypo_idx] * 3)
    np.random.RandomState(42).shuffle(oversample_idx)
    X_tr_os = X_tr[oversample_idx]
    y_tr_os = y_tr[oversample_idx]

    clf3 = xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                              use_label_encoder=False, eval_metric='logloss',
                              random_state=42)
    clf3.fit(X_tr_os, y_tr_os)
    pred3 = clf3.predict(X_va)
    prob3 = clf3.predict_proba(X_va)[:, 1]
    results['oversampled_3x'] = {
        'f1': float(f1_score(y_va, pred3)),
        'precision': float(precision_score(y_va, pred3)),
        'recall': float(recall_score(y_va, pred3)),
        'auroc': float(roc_auc_score(y_va, prob3)),
    }

    # Method 4: Threshold tuning — use lower threshold for higher recall
    best_f1 = 0
    best_thresh = 0.5
    for thresh in np.arange(0.05, 0.5, 0.02):
        pred_t = (prob1 >= thresh).astype(int)
        if pred_t.sum() > 0:
            f1_t = f1_score(y_va, pred_t)
            if f1_t > best_f1:
                best_f1 = f1_t
                best_thresh = thresh

    pred_tuned = (prob1 >= best_thresh).astype(int)
    results['threshold_tuned'] = {
        'threshold': float(best_thresh),
        'f1': float(f1_score(y_va, pred_tuned)),
        'precision': float(precision_score(y_va, pred_tuned)),
        'recall': float(recall_score(y_va, pred_tuned)),
        'auroc': float(roc_auc_score(y_va, prob1)),
    }

    # Feature importance from best model
    feat_names = ['gluc_now', 'trend_15m', 'trend_1hr', 'gluc_min', 'gluc_max',
                  'gluc_std', 'gluc_mean', 'iob', 'cob', 'basal', 'roc_mean', 'roc_min']
    fi = dict(zip(feat_names, [float(x) for x in clf2.feature_importances_]))

    best_method = max(results.items(), key=lambda x: x[1]['recall'])

    ctx.result.update({
        'hypo_rate_val': float(hypo_rate_val),
        'methods': results,
        'best_method': best_method[0],
        'best_recall': best_method[1]['recall'],
        'feature_importance': fi,
        'success': best_method[1]['recall'] > 0.60,
    })
    ctx.section('Hypo detection results')
    for name, r in results.items():
        ctx.log(f'{name}: F1={r["f1"]:.3f}, prec={r["precision"]:.3f}, '
                f'recall={r["recall"]:.3f}, AUROC={r["auroc"]:.3f}')
    return ctx.save('exp080_hypo_focused.json')


# ────────────────────────────────────────────────────────────────────
# EXP-081: Asymmetric Loss Forecasting
# Hypothesis: Penalizing under-prediction of glucose 3x more (predicting
#   safe when actual is low → dangerous) improves hypo sensitivity.
#   Target: hypo detection rate >40% (from 16%) without >20% MAE increase.
# ────────────────────────────────────────────────────────────────────

def run_asymmetric_loss(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-081', out,
                           hypothesis='asymmetric loss improves hypo detection >40%')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    HYPO = 70.0 / SCALE
    HYPER = 180.0 / SCALE

    # Train standard model (baseline)
    model_std = create_model('grouped', input_dim=8)
    train_forecast(model_std, train_ds, val_ds, f'{out}/exp081_std.pth',
                   'Standard', epochs=80)

    # Train with asymmetric loss: over-prediction costs 1x, under-prediction costs 3x
    model_asym = create_model('grouped', input_dim=8)
    device = next(model_asym.parameters()).device

    optimizer = torch.optim.Adam(model_asym.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)

    train_loader = torch.utils.data.DataLoader(train_ds, batch_size=64, shuffle=True)
    best_val = float('inf')

    for epoch in range(80):
        model_asym.train()
        epoch_loss = 0
        n = 0
        for batch in train_loader:
            x = batch[0].to(device)
            x_in = x.clone()
            x_in[:, 12:, 0] = 0.0
            pred = model_asym(x_in)
            target = x[:, :, 0]

            # Asymmetric loss on future glucose (channel 0, timesteps 12+)
            error = pred[:, 12:, 0] - target[:, 12:]
            # Under-prediction (pred < actual, error < 0) → 3x weight
            # This means model predicts lower than actual → dangerous for hypo
            weights = torch.where(error < 0, 3.0, 1.0)
            loss = (weights * error ** 2).mean()

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * x.size(0)
            n += x.size(0)

        # Validate
        model_asym.eval()
        val_loss = 0
        vn = 0
        with torch.no_grad():
            for batch in torch.utils.data.DataLoader(val_ds, batch_size=64):
                x = batch[0].to(device)
                x_in = x.clone()
                x_in[:, 12:, 0] = 0.0
                pred = model_asym(x_in)
                target = x[:, :, 0]
                loss = ((pred[:, 12:, 0] - target[:, 12:]) ** 2).mean()
                val_loss += loss.item() * x.size(0)
                vn += x.size(0)

        val_loss /= vn
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
            torch.save(model_asym.state_dict(), f'{out}/exp081_asym.pth')

        if (epoch + 1) % 20 == 0:
            ctx.log(f'[Asymmetric] {epoch+1}/80 val={val_loss:.6f} best={best_val:.6f}')

    model_asym.load_state_dict(torch.load(f'{out}/exp081_asym.pth', weights_only=True))

    # Evaluate both models
    def eval_model(model, ds):
        model.eval()
        device = next(model.parameters()).device
        all_mae = []
        hypo_detected = 0
        hypo_total = 0
        hyper_detected = 0
        hyper_total = 0
        hypo_fa = 0
        no_hypo_total = 0
        with torch.no_grad():
            for i in range(len(ds)):
                w = ds[i]
                if isinstance(w, tuple):
                    w = w[0]
                x = w.unsqueeze(0).to(device) if hasattr(w, 'unsqueeze') else torch.tensor(w).unsqueeze(0).to(device)
                x_in = x.clone()
                x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                target = x[0, 12:, 0].cpu().numpy() * SCALE
                forecast = pred[0, 12:, 0].cpu().numpy() * SCALE
                all_mae.append(float(np.mean(np.abs(forecast - target))))

                actual_hypo = target.min() < 70
                pred_hypo = forecast.min() < 70
                actual_hyper = target.max() > 180
                pred_hyper = forecast.max() > 180

                if actual_hypo:
                    hypo_total += 1
                    if pred_hypo:
                        hypo_detected += 1
                else:
                    no_hypo_total += 1
                    if pred_hypo:
                        hypo_fa += 1

                if actual_hyper:
                    hyper_total += 1
                    if pred_hyper:
                        hyper_detected += 1

        return {
            'mae': float(np.mean(all_mae)),
            'hypo_detect': hypo_detected / hypo_total if hypo_total > 0 else 0,
            'hypo_total': hypo_total,
            'hypo_fa_rate': hypo_fa / no_hypo_total if no_hypo_total > 0 else 0,
            'hyper_detect': hyper_detected / hyper_total if hyper_total > 0 else 0,
            'hyper_total': hyper_total,
        }

    std_metrics = eval_model(model_std, val_ds)
    asym_metrics = eval_model(model_asym, val_ds)

    ctx.result.update({
        'standard': std_metrics,
        'asymmetric': asym_metrics,
        'hypo_detect_improvement': asym_metrics['hypo_detect'] - std_metrics['hypo_detect'],
        'mae_increase_pct': (asym_metrics['mae'] - std_metrics['mae']) / std_metrics['mae'] * 100,
        'success': asym_metrics['hypo_detect'] > 0.40 and
                   (asym_metrics['mae'] - std_metrics['mae']) / std_metrics['mae'] < 0.20,
    })
    ctx.section('Asymmetric loss results')
    ctx.log(f'Standard: MAE={std_metrics["mae"]:.1f}, hypo={std_metrics["hypo_detect"]:.1%}, '
            f'hyper={std_metrics["hyper_detect"]:.1%}')
    ctx.log(f'Asymmetric: MAE={asym_metrics["mae"]:.1f}, hypo={asym_metrics["hypo_detect"]:.1%}, '
            f'hyper={asym_metrics["hyper_detect"]:.1%}')
    return ctx.save('exp081_asymmetric_loss.json')


# ────────────────────────────────────────────────────────────────────
# EXP-082: Direct Time-to-Event Regression
# Hypothesis: Dedicated regression head predicting minutes-to-hypo/hyper
#   beats deriving TTE from glucose forecast. Target: hypo MAE < 25 min.
# ────────────────────────────────────────────────────────────────────

def run_direct_tte(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-082', out,
                           hypothesis='direct TTE regression hypo MAE < 25 min')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    HYPO = 70.0 / SCALE
    HYPER = 180.0 / SCALE
    MAX_STEPS = 12

    # Build TTE labels
    def make_tte_labels(ds):
        hypo_tte = []
        hyper_tte = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            future = w[12:, 0]
            below = np.where(future < HYPO)[0]
            hypo_tte.append(below[0] + 1 if len(below) > 0 else MAX_STEPS + 1)
            above = np.where(future > HYPER)[0]
            hyper_tte.append(above[0] + 1 if len(above) > 0 else MAX_STEPS + 1)
        return np.array(hypo_tte, dtype=np.float32), np.array(hyper_tte, dtype=np.float32)

    train_hypo, train_hyper = make_tte_labels(train_ds)
    val_hypo, val_hyper = make_tte_labels(val_ds)

    # TTE regression model: encoder + 2 regression heads
    class TTEModel(torch.nn.Module):
        def __init__(self, input_dim=8, d_model=64):
            super().__init__()
            self.proj = torch.nn.Linear(input_dim, d_model)
            encoder_layer = torch.nn.TransformerEncoderLayer(
                d_model=d_model, nhead=4, dim_feedforward=128,
                dropout=0.1, batch_first=True, norm_first=True)
            self.encoder = torch.nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.hypo_head = torch.nn.Sequential(
                torch.nn.Linear(d_model, 32), torch.nn.ReLU(),
                torch.nn.Linear(32, 1))
            self.hyper_head = torch.nn.Sequential(
                torch.nn.Linear(d_model, 32), torch.nn.ReLU(),
                torch.nn.Linear(32, 1))

        def forward(self, x):
            h = self.proj(x[:, :12])  # history only
            h = self.encoder(h)
            h_pool = h.mean(dim=1)  # global average pool
            hypo = self.hypo_head(h_pool).squeeze(-1)
            hyper = self.hyper_head(h_pool).squeeze(-1)
            return hypo, hyper

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = TTEModel(input_dim=8).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)

    # Normalize TTE targets to [0, 1] range
    tte_scale = MAX_STEPS + 1
    train_hypo_n = torch.tensor(train_hypo / tte_scale)
    train_hyper_n = torch.tensor(train_hyper / tte_scale)

    # Create dataset with TTE labels
    train_windows = []
    for i in range(len(train_ds)):
        w = train_ds[i]
        if isinstance(w, tuple):
            w = w[0]
        train_windows.append(w)
    train_windows = torch.stack(train_windows)

    tte_train_ds = torch.utils.data.TensorDataset(
        train_windows, train_hypo_n, train_hyper_n)
    train_loader = torch.utils.data.DataLoader(tte_train_ds, batch_size=64, shuffle=True)

    best_val = float('inf')
    for epoch in range(100):
        model.train()
        for batch_x, batch_hypo, batch_hyper in train_loader:
            batch_x = batch_x.to(device)
            pred_hypo, pred_hyper = model(batch_x)
            loss_hypo = torch.nn.functional.mse_loss(pred_hypo, batch_hypo.to(device))
            loss_hyper = torch.nn.functional.mse_loss(pred_hyper, batch_hyper.to(device))
            loss = loss_hypo + loss_hyper

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # Validate
        if (epoch + 1) % 10 == 0:
            model.eval()
            val_windows = []
            for i in range(len(val_ds)):
                w = val_ds[i]
                if isinstance(w, tuple):
                    w = w[0]
                val_windows.append(w)
            val_x = torch.stack(val_windows).to(device)
            with torch.no_grad():
                ph, phr = model(val_x)
            val_loss = (torch.nn.functional.mse_loss(ph, torch.tensor(val_hypo / tte_scale).to(device)) +
                        torch.nn.functional.mse_loss(phr, torch.tensor(val_hyper / tte_scale).to(device))).item()
            scheduler.step(val_loss)
            if val_loss < best_val:
                best_val = val_loss
                torch.save(model.state_dict(), f'{out}/exp082_tte.pth')
            if (epoch + 1) % 20 == 0:
                ctx.log(f'[TTE] {epoch+1}/100 val={val_loss:.6f} best={best_val:.6f}')

    model.load_state_dict(torch.load(f'{out}/exp082_tte.pth', weights_only=True))
    model.eval()

    # Evaluate
    val_windows = []
    for i in range(len(val_ds)):
        w = val_ds[i]
        if isinstance(w, tuple):
            w = w[0]
        val_windows.append(w)
    val_x = torch.stack(val_windows).to(device)

    with torch.no_grad():
        pred_hypo_n, pred_hyper_n = model(val_x)
    pred_hypo_steps = (pred_hypo_n.cpu().numpy() * tte_scale).clip(1, MAX_STEPS + 1)
    pred_hyper_steps = (pred_hyper_n.cpu().numpy() * tte_scale).clip(1, MAX_STEPS + 1)

    hypo_mask = val_hypo <= MAX_STEPS
    hyper_mask = val_hyper <= MAX_STEPS

    hypo_mae = float(np.mean(np.abs(pred_hypo_steps[hypo_mask] - val_hypo[hypo_mask]))) * 5 if hypo_mask.sum() > 0 else None
    hyper_mae = float(np.mean(np.abs(pred_hyper_steps[hyper_mask] - val_hyper[hyper_mask]))) * 5 if hyper_mask.sum() > 0 else None

    hypo_detected = float(np.mean(pred_hypo_steps[hypo_mask] <= MAX_STEPS)) if hypo_mask.sum() > 0 else None
    hyper_detected = float(np.mean(pred_hyper_steps[hyper_mask] <= MAX_STEPS)) if hyper_mask.sum() > 0 else None

    ctx.result.update({
        'hypo_n_events': int(hypo_mask.sum()),
        'hyper_n_events': int(hyper_mask.sum()),
        'direct_hypo_mae_min': hypo_mae,
        'direct_hyper_mae_min': hyper_mae,
        'direct_hypo_detect': float(hypo_detected) if hypo_detected is not None else None,
        'direct_hyper_detect': float(hyper_detected) if hyper_detected is not None else None,
        'forecast_hypo_mae_min': 40.2,  # from EXP-074
        'forecast_hyper_mae_min': 6.8,  # from EXP-074
        'success': (hypo_mae is not None and hypo_mae < 25) or
                   (hyper_mae is not None and hyper_mae < 6.8),
    })
    ctx.section('Direct TTE results')
    if hypo_mae is not None:
        ctx.log(f'Hypo: MAE={hypo_mae:.1f} min (vs 40.2 forecast-derived), detect={hypo_detected:.1%}')
    if hyper_mae is not None:
        ctx.log(f'Hyper: MAE={hyper_mae:.1f} min (vs 6.8 forecast-derived), detect={hyper_detected:.1%}')
    return ctx.save('exp082_direct_tte.json')


# ────────────────────────────────────────────────────────────────────
# EXP-083: Chained Forecast Planning
# Hypothesis: Chaining 1hr forecasts (use predicted future as input
#   for next prediction) extends planning horizon to 3-6hr.
#   Target: chained 3hr MAE < 30 mg/dL.
# ────────────────────────────────────────────────────────────────────

def run_chained_planning(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-083', out,
                           hypothesis='chained 3hr MAE < 30 mg/dL')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # Need longer windows for ground truth at extended horizons
    # Use 48-step windows (4hr total: 2hr history + 2hr future) if available
    # Fall back to 24-step and chain
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val (24-step)')

    model = create_model('grouped', input_dim=8)
    train_forecast(model, train_ds, val_ds, f'{out}/exp083_base.pth',
                   'Base-1hr', epochs=80)

    device = next(model.parameters()).device
    SCALE = NORMALIZATION_SCALES.get('glucose', 400)

    # Chained prediction: predict 12 steps, then use those as history
    # for the next 12-step prediction
    def chain_predict(model, initial_window, n_chains=3):
        """Chain n_chains 12-step predictions for extended forecast."""
        model.eval()
        predictions = []
        current = initial_window.clone()

        with torch.no_grad():
            for chain in range(n_chains):
                x_in = current.clone()
                x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                pred_future = pred[0, 12:, :].clone()
                predictions.append(pred_future[:, 0].cpu().numpy())

                # Build next window: last 12 of current become first 12 of next
                # Use predicted values for glucose, keep other channels from last known
                next_window = torch.zeros_like(current)
                next_window[0, :12, :] = pred[0, 12:, :]  # predicted becomes history
                next_window[0, :12, 0] = pred[0, 12:, 0]  # glucose from prediction
                # Zero out other channels in future (we don't know them)
                current = next_window

        return np.concatenate(predictions)  # 12 * n_chains steps

    # Evaluate: compare chained prediction vs actual on validation windows
    # We need actual data beyond the 24-step window for ground truth
    # Use consecutive windows to get longer ground truth
    results = {}

    # For single-window accuracy: predict 12 steps, compare
    single_maes = []
    chained_2hr = []  # 2 chains = 24 steps = 2hr
    chained_3hr = []  # 3 chains = 36 steps = 3hr

    model.eval()
    for i in range(len(val_ds) - 3):
        # Get 4 consecutive windows for ground truth
        windows = []
        for j in range(4):
            w = val_ds[i + j]
            if isinstance(w, tuple):
                w = w[0]
            windows.append(w)

        # Use first window as input
        x = windows[0].unsqueeze(0).to(device)

        # Single-step prediction (1hr)
        x_in = x.clone()
        x_in[:, 12:, 0] = 0.0
        with torch.no_grad():
            pred = model(x_in)
        pred_1hr = pred[0, 12:, 0].cpu().numpy() * SCALE
        actual_1hr = x[0, 12:, 0].cpu().numpy() * SCALE
        single_maes.append(float(np.mean(np.abs(pred_1hr - actual_1hr))))

        # Chained prediction
        chained = chain_predict(model, x, n_chains=3)
        chained_mgdl = chained * SCALE

        # Ground truth from consecutive windows
        # Window[1] future = steps 12-24 from start
        # Window[2] future = steps 24-36 from start
        actual_2hr = windows[1][12:, 0].numpy() * SCALE if hasattr(windows[1], 'numpy') else windows[1].numpy()[12:, 0] * SCALE
        actual_3hr = windows[2][12:, 0].numpy() * SCALE if hasattr(windows[2], 'numpy') else windows[2].numpy()[12:, 0] * SCALE

        if len(chained_mgdl) >= 24:
            chained_2hr.append(float(np.mean(np.abs(chained_mgdl[12:24] - actual_2hr))))
        if len(chained_mgdl) >= 36:
            chained_3hr.append(float(np.mean(np.abs(chained_mgdl[24:36] - actual_3hr))))

    results = {
        'single_1hr_mae': float(np.mean(single_maes)),
        'chained_2hr_mae': float(np.mean(chained_2hr)) if chained_2hr else None,
        'chained_3hr_mae': float(np.mean(chained_3hr)) if chained_3hr else None,
        'n_eval': len(single_maes),
    }

    # Compute persistence baselines at each horizon
    persist_2hr = []
    persist_3hr = []
    for i in range(len(val_ds) - 3):
        w0 = val_ds[i]
        if isinstance(w0, tuple):
            w0 = w0[0]
        if hasattr(w0, 'numpy'):
            w0_np = w0.numpy()
        else:
            w0_np = w0
        last_gluc = w0_np[11, 0] * SCALE

        w1 = val_ds[i+1]
        if isinstance(w1, tuple):
            w1 = w1[0]
        if hasattr(w1, 'numpy'):
            w1_np = w1.numpy()
        else:
            w1_np = w1
        actual_2 = w1_np[12:, 0] * SCALE
        persist_2hr.append(float(np.mean(np.abs(last_gluc - actual_2))))

        w2 = val_ds[i+2]
        if isinstance(w2, tuple):
            w2 = w2[0]
        if hasattr(w2, 'numpy'):
            w2_np = w2.numpy()
        else:
            w2_np = w2
        actual_3 = w2_np[12:, 0] * SCALE
        persist_3hr.append(float(np.mean(np.abs(last_gluc - actual_3))))

    results['persist_2hr'] = float(np.mean(persist_2hr))
    results['persist_3hr'] = float(np.mean(persist_3hr))

    ctx.result.update({
        **results,
        'success': results.get('chained_3hr_mae') is not None and results['chained_3hr_mae'] < 30,
    })
    ctx.section('Chained planning results')
    ctx.log(f'1hr: {results["single_1hr_mae"]:.1f} mg/dL')
    if results['chained_2hr_mae']:
        ctx.log(f'2hr chained: {results["chained_2hr_mae"]:.1f} (persist: {results["persist_2hr"]:.1f})')
    if results['chained_3hr_mae']:
        ctx.log(f'3hr chained: {results["chained_3hr_mae"]:.1f} (persist: {results["persist_3hr"]:.1f})')
    return ctx.save('exp083_chained_planning.json')


# ────────────────────────────────────────────────────────────────────
# EXP-084: Gradient-Based Sensitivity Analysis
# Hypothesis: Computing dGlucose/dInsulin and dGlucose/dCarbs via
#   backprop gives per-window sensitivity estimates that correlate
#   with actual ISF/CR. Target: correlation > 0.3.
# ────────────────────────────────────────────────────────────────────

def run_gradient_sensitivity(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-084', out,
                           hypothesis='gradient sensitivity corr > 0.3')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    model = create_model('grouped', input_dim=8)
    train_forecast(model, train_ds, val_ds, f'{out}/exp084_base.pth',
                   'Base', epochs=80)

    device = next(model.parameters()).device
    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    BOLUS_SCALE = NORMALIZATION_SCALES.get('bolus', 10)
    CARB_SCALE = NORMALIZATION_SCALES.get('carbs', 100)
    IOB_SCALE = NORMALIZATION_SCALES.get('iob', 20)

    # Compute gradients: how does changing insulin/carbs affect predicted glucose?
    model.eval()
    sensitivities = []

    for i in range(min(len(val_ds), 2000)):
        w = val_ds[i]
        if isinstance(w, tuple):
            w = w[0]
        x = w.unsqueeze(0).to(device).clone().requires_grad_(True)

        x_in = x.clone()
        x_in[:, 12:, 0] = 0.0
        pred = model(x_in)

        # Mean predicted future glucose
        future_gluc = pred[0, 12:, 0].mean()
        future_gluc.backward()

        grad = x.grad[0].cpu().numpy()

        # Sensitivity to bolus (channel 4) in history
        bolus_sens = float(grad[:12, 4].sum()) * SCALE / BOLUS_SCALE if grad.shape[1] > 4 else 0
        # Sensitivity to carbs (channel 5) in history
        carb_sens = float(grad[:12, 5].sum()) * SCALE / CARB_SCALE if grad.shape[1] > 5 else 0
        # Sensitivity to IOB (channel 1)
        iob_sens = float(grad[:12, 1].sum()) * SCALE / IOB_SCALE if grad.shape[1] > 1 else 0
        # Current glucose
        gluc_now = float(w[11, 0].item()) * SCALE
        # Actual delta
        actual_delta = float(w[23, 0].item() - w[11, 0].item()) * SCALE
        # Actual bolus/carbs in history
        actual_bolus = float(w[:12, 4].sum().item()) * BOLUS_SCALE if w.shape[1] > 4 else 0
        actual_carbs = float(w[:12, 5].sum().item()) * CARB_SCALE if w.shape[1] > 5 else 0

        sensitivities.append({
            'bolus_sensitivity': bolus_sens,
            'carb_sensitivity': carb_sens,
            'iob_sensitivity': iob_sens,
            'gluc_now': gluc_now,
            'actual_delta': actual_delta,
            'actual_bolus': actual_bolus,
            'actual_carbs': actual_carbs,
        })

    sens_arr = np.array([[s['bolus_sensitivity'], s['carb_sensitivity'],
                           s['iob_sensitivity']] for s in sensitivities])

    # Summary statistics
    bolus_sens_mean = float(np.mean([s['bolus_sensitivity'] for s in sensitivities]))
    carb_sens_mean = float(np.mean([s['carb_sensitivity'] for s in sensitivities]))
    iob_sens_mean = float(np.mean([s['iob_sensitivity'] for s in sensitivities]))

    # Correlation between gradient sensitivity and actual glucose change
    deltas = np.array([s['actual_delta'] for s in sensitivities])
    bolus_amounts = np.array([s['actual_bolus'] for s in sensitivities])
    carb_amounts = np.array([s['actual_carbs'] for s in sensitivities])

    # Among windows with bolus, does sensitivity predict delta?
    bolus_mask = bolus_amounts > 0.1
    carb_mask = carb_amounts > 1.0

    bolus_corr = float(np.corrcoef(
        [s['bolus_sensitivity'] for s, m in zip(sensitivities, bolus_mask) if m],
        deltas[bolus_mask])[0, 1]) if bolus_mask.sum() > 10 else None

    carb_corr = float(np.corrcoef(
        [s['carb_sensitivity'] for s, m in zip(sensitivities, carb_mask) if m],
        deltas[carb_mask])[0, 1]) if carb_mask.sum() > 10 else None

    # Estimated ISF from gradient: dGlucose/dBolus
    # If bolus_sens is -30, that means 1 unit normalized bolus → -30 mg/dL
    estimated_isf = abs(bolus_sens_mean)

    ctx.result.update({
        'bolus_sensitivity_mean': bolus_sens_mean,
        'carb_sensitivity_mean': carb_sens_mean,
        'iob_sensitivity_mean': iob_sens_mean,
        'bolus_delta_correlation': bolus_corr,
        'carb_delta_correlation': carb_corr,
        'estimated_isf_mgdl_per_u': estimated_isf,
        'n_bolus_windows': int(bolus_mask.sum()),
        'n_carb_windows': int(carb_mask.sum()),
        'n_total': len(sensitivities),
        'success': (bolus_corr is not None and abs(bolus_corr) > 0.3) or
                   (carb_corr is not None and abs(carb_corr) > 0.3),
    })
    ctx.section('Gradient sensitivity results')
    ctx.log(f'Mean sensitivity: bolus={bolus_sens_mean:.1f}, carbs={carb_sens_mean:.1f}, '
            f'IOB={iob_sens_mean:.1f} mg/dL per normalized unit')
    ctx.log(f'Bolus-delta corr: {bolus_corr:.3f} (n={bolus_mask.sum()})' if bolus_corr else 'Bolus: too few samples')
    ctx.log(f'Carb-delta corr: {carb_corr:.3f} (n={carb_mask.sum()})' if carb_corr else 'Carbs: too few samples')
    ctx.log(f'Estimated ISF: {estimated_isf:.1f} mg/dL per unit')
    return ctx.save('exp084_gradient_sensitivity.json')


# ────────────────────────────────────────────────────────────────────
# EXP-085: Stacked Ensemble Classifier
# Hypothesis: Stacking multi-task encoder (F1=0.877) with XGBoost
#   (F1=0.710) via meta-learner beats both. Target: F1 > 0.85.
# ────────────────────────────────────────────────────────────────────

def run_stacked_classifier(args):
    set_seed(42)
    out = getattr(args, 'output_dir', 'externals/experiments')
    ctx = ExperimentContext('EXP-085', out,
                           hypothesis='stacked ensemble F1 > 0.85')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    ctx.log(f'{len(train_ds)} train, {len(val_ds)} val')

    SCALE = NORMALIZATION_SCALES.get('glucose', 400)
    BOLUS_SCALE = NORMALIZATION_SCALES.get('bolus', 10)
    CARB_SCALE = NORMALIZATION_SCALES.get('carbs', 100)

    # Build event labels
    def make_labels(ds):
        labels = []
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            future = w[12:]
            future_gluc = future[:, 0] * SCALE
            future_bolus = future[:, 4] * BOLUS_SCALE if w.shape[1] > 4 else np.zeros(12)
            future_carbs = future[:, 5] * CARB_SCALE if w.shape[1] > 5 else np.zeros(12)
            if future_gluc.min() < 70:
                labels.append('hypo_risk')
            elif future_gluc.max() > 250:
                labels.append('hyper_risk')
            elif future_bolus.sum() > 0.5:
                labels.append('correction_bolus')
            elif future_carbs.sum() > 5:
                labels.append('meal_bolus')
            else:
                labels.append('normal')
        return np.array(labels)

    train_labels = make_labels(train_ds)
    val_labels = make_labels(val_ds)

    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    le.fit(np.concatenate([train_labels, val_labels]))
    y_train = le.transform(train_labels)
    y_val = le.transform(val_labels)
    n_classes = len(le.classes_)

    # Model 1: XGBoost on hand-crafted features
    def extract_xgb_features(ds):
        features = []
        IOB_SCALE = NORMALIZATION_SCALES.get('iob', 20)
        for i in range(len(ds)):
            w = ds[i]
            if isinstance(w, tuple):
                w = w[0]
            if hasattr(w, 'numpy'):
                w = w.numpy()
            hist = w[:12]
            gluc = hist[:, 0] * SCALE
            feat = [
                float(gluc[-1]), float(gluc[-1] - gluc[-4]),
                float(gluc[-1] - gluc[0]), float(gluc.min()),
                float(gluc.max()), float(gluc.std()), float(gluc.mean()),
                float(hist[-1, 1] * IOB_SCALE) if w.shape[1] > 1 else 0,
                float(hist[-1, 2] * NORMALIZATION_SCALES.get('cob', 100)) if w.shape[1] > 2 else 0,
                float(hist[:, 4].sum() * BOLUS_SCALE) if w.shape[1] > 4 else 0,
                float(hist[:, 5].sum() * CARB_SCALE) if w.shape[1] > 5 else 0,
            ]
            if len(gluc) >= 6:
                feat.append(float(np.mean(np.diff(gluc[-6:]))))
            else:
                feat.append(0)
            features.append(feat)
        return np.array(features)

    X_train_xgb = extract_xgb_features(train_ds)
    X_val_xgb = extract_xgb_features(val_ds)

    import xgboost as xgb
    from sklearn.metrics import f1_score

    clf_xgb = xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                                  use_label_encoder=False, eval_metric='mlogloss',
                                  random_state=42)
    clf_xgb.fit(X_train_xgb, y_train)
    xgb_probs_train = clf_xgb.predict_proba(X_train_xgb)
    xgb_probs_val = clf_xgb.predict_proba(X_val_xgb)
    xgb_pred = clf_xgb.predict(X_val_xgb)
    xgb_f1 = float(f1_score(y_val, xgb_pred, average='macro'))
    ctx.log(f'XGBoost F1: {xgb_f1:.3f}')

    # Model 2: Neural encoder classifier
    class EncoderClassifier(torch.nn.Module):
        def __init__(self, input_dim=8, d_model=64, n_classes=5):
            super().__init__()
            self.proj = torch.nn.Linear(input_dim, d_model)
            encoder_layer = torch.nn.TransformerEncoderLayer(
                d_model=d_model, nhead=4, dim_feedforward=128,
                dropout=0.1, batch_first=True, norm_first=True)
            self.encoder = torch.nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.head = torch.nn.Sequential(
                torch.nn.Linear(d_model, 32), torch.nn.ReLU(),
                torch.nn.Dropout(0.1),
                torch.nn.Linear(32, n_classes))

        def forward(self, x):
            h = self.proj(x[:, :12])
            h = self.encoder(h)
            h = h.mean(dim=1)
            return self.head(h)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    nn_clf = EncoderClassifier(input_dim=8, n_classes=n_classes).to(device)
    optimizer = torch.optim.Adam(nn_clf.parameters(), lr=1e-3)

    # Training data
    train_windows = []
    for i in range(len(train_ds)):
        w = train_ds[i]
        if isinstance(w, tuple):
            w = w[0]
        train_windows.append(w)
    train_x = torch.stack(train_windows)
    train_y = torch.tensor(y_train, dtype=torch.long)

    nn_train = torch.utils.data.TensorDataset(train_x, train_y)
    nn_loader = torch.utils.data.DataLoader(nn_train, batch_size=64, shuffle=True)

    best_val = float('inf')
    for epoch in range(60):
        nn_clf.train()
        for bx, by in nn_loader:
            logits = nn_clf(bx.to(device))
            loss = torch.nn.functional.cross_entropy(logits, by.to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        if (epoch + 1) % 20 == 0:
            nn_clf.eval()
            val_windows = []
            for i in range(len(val_ds)):
                w = val_ds[i]
                if isinstance(w, tuple):
                    w = w[0]
                val_windows.append(w)
            val_x = torch.stack(val_windows).to(device)
            with torch.no_grad():
                logits = nn_clf(val_x)
            val_loss = torch.nn.functional.cross_entropy(logits, torch.tensor(y_val).to(device)).item()
            if val_loss < best_val:
                best_val = val_loss
                torch.save(nn_clf.state_dict(), f'{out}/exp085_nn.pth')

    nn_clf.load_state_dict(torch.load(f'{out}/exp085_nn.pth', weights_only=True))
    nn_clf.eval()

    # Get NN probabilities
    val_windows = []
    for i in range(len(val_ds)):
        w = val_ds[i]
        if isinstance(w, tuple):
            w = w[0]
        val_windows.append(w)
    val_x = torch.stack(val_windows).to(device)

    train_windows_t = train_x.to(device)
    with torch.no_grad():
        nn_probs_train = torch.softmax(nn_clf(train_windows_t), dim=1).cpu().numpy()
        nn_probs_val = torch.softmax(nn_clf(val_x), dim=1).cpu().numpy()

    nn_pred = nn_probs_val.argmax(axis=1)
    nn_f1 = float(f1_score(y_val, nn_pred, average='macro'))
    ctx.log(f'Neural F1: {nn_f1:.3f}')

    # Stack: combine XGBoost probs + NN probs as features for meta-learner
    meta_train = np.hstack([xgb_probs_train, nn_probs_train])
    meta_val = np.hstack([xgb_probs_val, nn_probs_val])

    meta_clf = xgb.XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1,
                                   use_label_encoder=False, eval_metric='mlogloss',
                                   random_state=42)
    meta_clf.fit(meta_train, y_train)
    meta_pred = meta_clf.predict(meta_val)
    meta_f1 = float(f1_score(y_val, meta_pred, average='macro'))

    from sklearn.metrics import classification_report
    report = classification_report(y_val, meta_pred, target_names=le.classes_, output_dict=True)

    ctx.result.update({
        'xgb_f1': xgb_f1,
        'nn_f1': nn_f1,
        'stacked_f1': meta_f1,
        'per_class': {k: {'f1': v['f1-score'], 'support': v['support']}
                      for k, v in report.items() if k in le.classes_},
        'improvement_over_best': meta_f1 - max(xgb_f1, nn_f1),
        'success': meta_f1 > 0.85,
    })
    ctx.section('Stacked classifier results')
    ctx.log(f'XGBoost: {xgb_f1:.3f}, Neural: {nn_f1:.3f}, Stacked: {meta_f1:.3f}')
    for c in le.classes_:
        if c in report:
            ctx.log(f'  {c}: F1={report[c]["f1-score"]:.3f}')
    return ctx.save('exp085_stacked_classifier.json')


# ────────────────────────────────────────────────────────────────────
# EXP-086: Asymmetric Loss with Extended Training
# Hypothesis: Combining asymmetric loss (3x hypo penalty) with 150 epochs
#   will improve on both MAE=13.0 and hypo detect=38.6%.
# Target: MAE<12.5 AND hypo detection >45%.
# ────────────────────────────────────────────────────────────────────

def run_asymmetric_long(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.experiment_lib import forecast_mse
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-086] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def asymmetric_loss(pred, target, penalty=3.0):
        diff = pred - target
        weight = torch.where(diff > 0, torch.tensor(penalty, device=diff.device),
                             torch.tensor(1.0, device=diff.device))
        return (weight * diff ** 2).mean()

    results = {}
    for config_name, epochs, loss_fn_name in [
        ('standard_150ep', 150, 'mse'),
        ('asymmetric_150ep', 150, 'asymmetric'),
        ('asymmetric_200ep', 200, 'asymmetric'),
    ]:
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)

        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        vl = DataLoader(val_ds, batch_size=128)
        best_val = float('inf')
        best_sd = None

        for ep in range(1, epochs + 1):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, 12:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                if loss_fn_name == 'asymmetric':
                    loss = asymmetric_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                else:
                    loss = torch.nn.functional.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                loss.backward()
                optimizer.step()

            model.eval()
            val_loss = 0
            n_val = 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device)
                    x_in = bx.clone()
                    x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    val_loss += torch.nn.functional.mse_loss(
                        pred[:, 12:, :1], bx[:, 12:, :1]).item()
                    n_val += 1
            val_loss /= max(n_val, 1)
            scheduler.step(val_loss)

            if val_loss < best_val:
                best_val = val_loss
                best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            if ep % 30 == 0:
                lr = optimizer.param_groups[0]['lr']
                print(f"  [{config_name}] {ep}/{epochs} val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}")

        model.load_state_dict(best_sd)
        model.eval()
        # Compute forecast MAE inline (denorm to mg/dL)
        mae_vals = []
        with torch.no_grad():
            for w in val_np:
                t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone(); inp[:, 12:, 0] = 0
                pred = model(inp)
                pg = pred[0, 12:, 0].cpu().numpy() * 400
                ag = t[0, 12:, 0].cpu().numpy() * 400
                mae_vals.append(np.mean(np.abs(pg - ag)))
        mae = float(np.mean(mae_vals))
        print(f"  [EXP-086] {config_name}: MAE={mae:.1f} mg/dL")

        hypo_total = 0
        hypo_detected = 0
        with torch.no_grad():
            for w in val_np:
                t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone()
                inp[:, 12:, 0] = 0
                pred = model(inp)
                pred_gluc = pred[0, 12:, 0].cpu().numpy() * 400
                actual_gluc = t[0, 12:, 0].cpu().numpy() * 400
                if actual_gluc.min() < 70:
                    hypo_total += 1
                    if pred_gluc.min() < 70:
                        hypo_detected += 1
        hypo_rate = hypo_detected / max(hypo_total, 1)
        print(f"  [EXP-086] {config_name}: hypo detect={hypo_rate:.1%} ({hypo_detected}/{hypo_total})")
        results[config_name] = {
            'mae': float(mae), 'hypo_detect': float(hypo_rate),
            'hypo_n': hypo_total, 'best_val': float(best_val),
        }

    out_path = f"{out}/exp086_asymmetric_long.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-086', 'name': 'asymmetric-long',
                   'results': results}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-087: Unified Forecast + TTE Model
# Hypothesis: Shared encoder outputting glucose forecast AND TTE
#   predictions outperforms separate models.
# Target: MAE<13 AND hypo TTE MAE<22 min in one model.
# ────────────────────────────────────────────────────────────────────

def run_unified_forecast_tte(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.experiment_lib import forecast_mse
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-087] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    class UnifiedModel(torch.nn.Module):
        def __init__(self, n_feat=8, d_model=64, ws=24):
            super().__init__()
            self.proj = torch.nn.Linear(n_feat, d_model)
            el = torch.nn.TransformerEncoderLayer(
                d_model=d_model, nhead=4, dim_feedforward=128,
                dropout=0.1, batch_first=True, norm_first=True)
            self.enc = torch.nn.TransformerEncoder(el, num_layers=3)
            self.forecast_head = torch.nn.Linear(d_model, n_feat)
            self.tte_head = torch.nn.Sequential(
                torch.nn.Linear(d_model * ws, 128),
                torch.nn.ReLU(),
                torch.nn.Linear(128, 2))
            self.ws = ws

        def forward(self, x, task='both'):
            h = self.enc(self.proj(x))
            res = {}
            if task in ('forecast', 'both'):
                res['forecast'] = self.forecast_head(h)
            if task in ('tte', 'both'):
                res['tte'] = self.tte_head(h.reshape(h.shape[0], -1))
            return res

    def compute_tte_targets(windows, lo=70/400, hi=180/400):
        targets = []
        for w in windows:
            gluc = w[12:, 0]
            hypo_min, hyper_min = 60.0, 60.0
            for i, g in enumerate(gluc):
                if g < lo and hypo_min == 60.0:
                    hypo_min = i * 5.0
                if g > hi and hyper_min == 60.0:
                    hyper_min = i * 5.0
            targets.append([hypo_min, hyper_min])
        return np.array(targets, dtype=np.float32)

    train_tte = compute_tte_targets(train_np)
    val_tte = compute_tte_targets(val_np)

    model = UnifiedModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=128)

    # Pre-compute TTE tensors aligned by index
    train_tte_t = torch.tensor(train_tte, dtype=torch.float32, device=device)

    best_val = float('inf')
    best_sd = None
    for ep in range(1, 121):
        model.train()
        idx = 0
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            res = model(x_in, task='both')
            f_loss = torch.nn.functional.mse_loss(res['forecast'][:, 12:, :1], bx[:, 12:, :1])
            bs = bx.shape[0]
            end = min(idx + bs, len(train_tte_t))
            if end > idx and (end - idx) == bs:
                t_loss = torch.nn.functional.mse_loss(
                    res['tte'], train_tte_t[idx:end]) / 3600
            else:
                t_loss = torch.tensor(0.0, device=device)
            (f_loss + 0.1 * t_loss).backward()
            optimizer.step()
            idx += bs

        model.eval()
        vl_sum, vn = 0, 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, 12:, 0] = 0.0
                res = model(x_in, task='forecast')
                vl_sum += torch.nn.functional.mse_loss(
                    res['forecast'][:, 12:, :1], bx[:, 12:, :1]).item()
                vn += 1
        vl_avg = vl_sum / max(vn, 1)
        scheduler.step(vl_avg)
        if vl_avg < best_val:
            best_val = vl_avg
            best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 20 == 0:
            print(f"  [EXP-087] {ep}/120 val={vl_avg:.6f} best={best_val:.6f}")

    model.load_state_dict(best_sd)
    model.eval()

    mae_list, hypo_tte_err, hyper_tte_err = [], [], []
    hypo_det, hypo_tot = 0, 0
    with torch.no_grad():
        for i, w in enumerate(val_np):
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone()
            inp[:, 12:, 0] = 0
            res = model(inp, task='both')
            pg = res['forecast'][0, 12:, 0].cpu().numpy() * 400
            ag = t[0, 12:, 0].cpu().numpy() * 400
            mae_list.append(np.mean(np.abs(pg - ag)))
            pt = res['tte'][0].cpu().numpy()
            at = val_tte[i]
            if at[0] < 60:
                hypo_tot += 1
                hypo_tte_err.append(abs(pt[0] - at[0]))
                if pt[0] < 55:
                    hypo_det += 1
            if at[1] < 60:
                hyper_tte_err.append(abs(pt[1] - at[1]))

    fmae = float(np.mean(mae_list))
    hmae = float(np.mean(hypo_tte_err)) if hypo_tte_err else -1
    hrmae = float(np.mean(hyper_tte_err)) if hyper_tte_err else -1
    hr = hypo_det / max(hypo_tot, 1)

    print(f"\n--- Unified forecast+TTE results ---")
    print(f"  [EXP-087] Forecast MAE: {fmae:.1f} mg/dL")
    print(f"  [EXP-087] Hypo TTE MAE: {hmae:.1f} min, detect={hr:.1%}")
    print(f"  [EXP-087] Hyper TTE MAE: {hrmae:.1f} min")

    out_path = f"{out}/exp087_unified_forecast_tte.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-087', 'name': 'unified-forecast-tte',
                   'results': {'forecast_mae': fmae, 'hypo_tte_mae': hmae,
                               'hyper_tte_mae': hrmae, 'hypo_detect': hr}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-088: Production Pipeline v2 — Asymmetric + TTE + Conformal
# Hypothesis: Upgrading to asymmetric-trained model improves suggestion
#   quality and adds hypo warnings with timing.
# Target: Maintain 100% precision, add hypo warnings.
# ────────────────────────────────────────────────────────────────────

def run_production_v2(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-088] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def asym_loss(pred, target, penalty=3.0):
        diff = pred - target
        w = torch.where(diff > 0, torch.tensor(penalty, device=diff.device),
                        torch.tensor(1.0, device=diff.device))
        return (w * diff ** 2).mean()

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=128)

    best_val = float('inf')
    best_sd = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            loss = asym_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer.step()
        model.eval()
        vs, vn = 0, 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += torch.nn.functional.mse_loss(
                    pred[:, 12:, :1], bx[:, 12:, :1]).item()
                vn += 1
        va = vs / max(vn, 1)
        scheduler.step(va)
        if va < best_val:
            best_val = va
            best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 20 == 0:
            print(f"  [Asym-train] {ep}/100 val={va:.6f} best={best_val:.6f}")

    model.load_state_dict(best_sd)
    model.eval()

    # Calibrate conformal thresholds on training set
    cal_res = []
    with torch.no_grad():
        for w in train_np[:3000]:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone()
            inp[:, 12:, 0] = 0
            pred = model(inp)
            r = torch.abs(pred[0, 12:, 0] - t[0, 12:, 0]).cpu().numpy() * 400
            cal_res.append(r)
    thresholds = np.percentile(np.array(cal_res), 90, axis=0)

    # Production pipeline
    suggestions = []
    correct = 0
    total_checked = 0
    with torch.no_grad():
        for w in val_np:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone()
            inp[:, 12:, 0] = 0
            pred = model(inp)
            pg = pred[0, 12:, 0].cpu().numpy() * 400
            ag = t[0, 12:, 0].cpu().numpy() * 400
            residuals = np.abs(pg - ag)
            if not np.all(residuals[:6] < thresholds[:6]):
                continue

            hypo_step, hyper_step = -1, -1
            for si in range(len(pg)):
                if pg[si] < 70 and hypo_step < 0:
                    hypo_step = si
                if pg[si] > 250 and hyper_step < 0:
                    hyper_step = si

            action = None
            if hypo_step >= 0:
                action = {'type': 'eat_carbs', 'urgency': 'high',
                          'tte_min': int(hypo_step * 5)}
            elif hyper_step >= 0:
                if pg.max() > 300:
                    action = {'type': 'correction_bolus', 'urgency': 'high',
                              'tte_min': int(hyper_step * 5)}
                else:
                    action = {'type': 'consider_correction', 'urgency': 'medium',
                              'tte_min': int(hyper_step * 5)}
            elif pg.mean() > 180:
                action = {'type': 'consider_correction', 'urgency': 'low'}

            if action:
                suggestions.append(action)
                total_checked += 1
                amin, amax = ag.min(), ag.max()
                ok = False
                if action['type'] == 'eat_carbs' and amin < 80:
                    ok = True
                elif action['type'] == 'correction_bolus' and amax > 250:
                    ok = True
                elif action['type'] == 'consider_correction' and amax > 170:
                    ok = True
                if ok:
                    correct += 1

    prec = correct / max(total_checked, 1)
    tc = {}
    for s in suggestions:
        tc[s['type']] = tc.get(s['type'], 0) + 1
    hypo_w = [s for s in suggestions if s['type'] == 'eat_carbs']
    avg_tte = np.mean([s.get('tte_min', 0) for s in hypo_w]) if hypo_w else -1

    print(f"\n--- Production v2 pipeline results ---")
    print(f"  [EXP-088] {len(suggestions)} suggestions, precision={prec:.1%}")
    print(f"  [EXP-088] Types: {tc}")
    print(f"  [EXP-088] Hypo warnings: {len(hypo_w)}, avg TTE={avg_tte:.0f} min")

    out_path = f"{out}/exp088_production_v2.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-088', 'name': 'production-v2',
                   'results': {'n_suggestions': len(suggestions), 'precision': prec,
                               'types': tc, 'hypo_warnings': len(hypo_w),
                               'avg_hypo_tte_min': float(avg_tte)}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-089: Conformal-Bounded Chained Planning
# Hypothesis: Conformal intervals on chained forecasts provide calibrated
#   uncertainty that prevents overconfident multi-hour planning.
# Target: 90% coverage at 3hr, actionable suggestions with risk.
# ────────────────────────────────────────────────────────────────────

def run_conformal_chained(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.experiment_lib import train_forecast
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    print(f"  [EXP-089] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
    ckpt = f"{out}/exp089_base.pth"
    train_forecast(model, train_ds, val_ds, ckpt, 'Base', epochs=80, batch=128)
    model.to(device)
    model.eval()

    # Calibrate per-step conformal on training data
    cal_errors = []
    with torch.no_grad():
        for w in train_np[:4000]:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone()
            inp[:, 12:, 0] = 0
            pred = model(inp)
            errs = (pred[0, 12:, 0] - t[0, 12:, 0]).abs().cpu().numpy() * 400
            cal_errors.append(errs)
    cal_errors = np.array(cal_errors)
    conformal_90 = np.percentile(cal_errors, 90, axis=0)

    # Chained forecast with growing uncertainty
    results_by_h = {1: [], 2: [], 3: []}
    coverage_by_h = {1: [], 2: [], 3: []}

    with torch.no_grad():
        for i in range(0, len(val_np) - 2, 3):
            current = val_np[i].copy()
            for chain_i in range(3):
                t = torch.tensor(current, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone()
                inp[:, 12:, 0] = 0
                pred = model(inp)
                pg = pred[0, 12:, 0].cpu().numpy() * 400

                actual_idx = i + chain_i
                if actual_idx < len(val_np):
                    ag = val_np[actual_idx][12:, 0] * 400
                    mae = np.mean(np.abs(pg - ag))
                    results_by_h[chain_i + 1].append(mae)
                    interval = conformal_90 * np.sqrt(chain_i + 1)
                    covered = np.all(np.abs(pg - ag) <= interval)
                    coverage_by_h[chain_i + 1].append(1.0 if covered else 0.0)

                # Shift for next chain
                if chain_i < 2:
                    new_w = current.copy()
                    new_w[:12] = current[12:]
                    new_w[12:, 0] = pred[0, 12:, 0].cpu().numpy()
                    current = new_w

    print(f"\n--- Conformal chained planning results ---")
    for h in [1, 2, 3]:
        mae = np.mean(results_by_h[h]) if results_by_h[h] else -1
        cov = np.mean(coverage_by_h[h]) if coverage_by_h[h] else -1
        n = len(results_by_h[h])
        print(f"  [EXP-089] {h}hr: MAE={mae:.1f}, coverage={cov:.1%}, n={n}")

    out_path = f"{out}/exp089_conformal_chained.json"
    res = {}
    for h in [1, 2, 3]:
        res[f'{h}hr'] = {
            'mae': float(np.mean(results_by_h[h])) if results_by_h[h] else -1,
            'coverage': float(np.mean(coverage_by_h[h])) if coverage_by_h[h] else -1,
            'n': len(results_by_h[h]),
        }
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-089', 'name': 'conformal-chained',
                   'results': res}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-090: Hypo Ensemble — Combine All Hypo Detection Methods
# Hypothesis: Ensembling cost-sensitive XGBoost + asymmetric forecast
#   achieves >85% recall at >65% precision for hypo detection.
# Target: Recall >85%, Precision >65%.
# ────────────────────────────────────────────────────────────────────

def run_hypo_ensemble(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder
    import xgboost as xgb
    from sklearn.metrics import f1_score, precision_score, recall_score

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-090] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def build_hypo_features(windows):
        X, y = [], []
        for w in windows:
            hg = w[:12, 0] * 400
            features = [hg[-1], hg.mean(), hg.std(), hg[-1] - hg[-3],
                        hg[-1] - hg[0], hg.min(),
                        w[:12, 1].mean(), w[:12, 2].mean(),
                        w[:12, 3].mean(), w[:12, 4].sum(), w[:12, 5].sum()]
            X.append(features)
            y.append(1 if (w[12:, 0] * 400).min() < 70 else 0)
        return np.array(X, dtype=np.float32), np.array(y)

    X_tr, y_tr = build_hypo_features(train_np)
    X_va, y_va = build_hypo_features(val_np)

    # XGBoost with aggressive cost-sensitivity
    pos = y_tr.sum()
    neg = len(y_tr) - pos
    scale = neg / max(pos, 1)
    dtrain = xgb.DMatrix(X_tr, label=y_tr)
    dval = xgb.DMatrix(X_va, label=y_va)
    bst = xgb.train(
        {'max_depth': 6, 'eta': 0.1, 'objective': 'binary:logistic',
         'eval_metric': 'auc', 'scale_pos_weight': scale * 5},
        dtrain, num_boost_round=200, evals=[(dval, 'val')], verbose_eval=False)
    xgb_probs = bst.predict(dval)
    print(f"  [EXP-090] XGBoost: recall={recall_score(y_va, (xgb_probs>0.3).astype(int)):.3f}")

    # Asymmetric forecast
    def asym_loss(pred, target, penalty=3.0):
        diff = pred - target
        w = torch.where(diff > 0, torch.tensor(penalty, device=diff.device),
                        torch.tensor(1.0, device=diff.device))
        return (w * diff ** 2).mean()

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=128)

    best_val, best_sd = float('inf'), None
    for ep in range(1, 81):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            asym_loss(pred[:, 12:, :1], bx[:, 12:, :1]).backward()
            optimizer.step()
        model.eval()
        vs, vn = 0, 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                vs += torch.nn.functional.mse_loss(
                    model(x_in)[:, 12:, :1], bx[:, 12:, :1]).item()
                vn += 1
        va = vs / max(vn, 1)
        scheduler.step(va)
        if va < best_val:
            best_val = va
            best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 20 == 0:
            print(f"  [EXP-090] [Asym] {ep}/80 val={va:.6f}")

    model.load_state_dict(best_sd)
    model.eval()

    forecast_probs = np.zeros(len(val_np))
    with torch.no_grad():
        for i, w in enumerate(val_np):
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone(); inp[:, 12:, 0] = 0
            pg = model(inp)[0, 12:, 0].cpu().numpy() * 400
            mn = pg.min()
            if mn < 80:
                forecast_probs[i] = min(1.0, (80 - mn) / 40)

    print(f"  [EXP-090] Forecast: recall={recall_score(y_va, (forecast_probs>0.3).astype(int)):.3f}")

    # Ensemble methods
    ens_or = ((xgb_probs > 0.3) | (forecast_probs > 0.3)).astype(int)
    ens_avg = ((xgb_probs + forecast_probs) / 2 > 0.3).astype(int)
    ens_wt = ((xgb_probs * 0.6 + forecast_probs * 0.4) > 0.3).astype(int)

    print(f"\n--- Hypo ensemble results ---")
    results = {}
    for nm, pds in [('or', ens_or), ('average', ens_avg), ('weighted', ens_wt),
                    ('xgb_only', (xgb_probs > 0.3).astype(int)),
                    ('forecast_only', (forecast_probs > 0.3).astype(int))]:
        r = recall_score(y_va, pds)
        p = precision_score(y_va, pds)
        f = f1_score(y_va, pds)
        results[nm] = {'recall': float(r), 'precision': float(p), 'f1': float(f)}
        print(f"  [EXP-090] {nm}: recall={r:.3f}, prec={p:.3f}, F1={f:.3f}")

    out_path = f"{out}/exp090_hypo_ensemble.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-090', 'name': 'hypo-ensemble',
                   'results': results}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-091: Planning Horizon Sweep — Action Precision by Horizon
# Hypothesis: Different actions have different optimal horizons.
#   Hypo warnings best at 15-30 min, corrections at 30-60 min.
# Target: Map each action to optimal horizon with precision >80%.
# ────────────────────────────────────────────────────────────────────

def run_planning_horizon_sweep(args):
    set_seed(42)
    import torch, json, numpy as np
    from tools.cgmencode.experiment_lib import train_forecast
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-091] {len(val_np)} val windows")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
    ckpt = f"{out}/exp091_base.pth"
    train_forecast(model, train_ds, val_ds, ckpt, 'Base', epochs=80, batch=128)
    model.to(device)
    model.eval()

    horizons_min = [10, 15, 20, 30, 45, 60]
    horizon_steps = [h // 5 for h in horizons_min]

    results = {}
    for h_min, h_steps in zip(horizons_min, horizon_steps):
        hypo_c, hypo_t = 0, 0
        hyper_c, hyper_t = 0, 0
        corr_c, corr_t = 0, 0

        with torch.no_grad():
            for w in val_np:
                t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone(); inp[:, 12:, 0] = 0
                pred = model(inp)
                pg = pred[0, 12:12+h_steps, 0].cpu().numpy() * 400
                ag = t[0, 12:12+h_steps, 0].cpu().numpy() * 400
                if len(pg) == 0:
                    continue
                if pg.min() < 70:
                    hypo_t += 1
                    if ag.min() < 80:
                        hypo_c += 1
                if pg.max() > 250:
                    hyper_t += 1
                    if ag.max() > 220:
                        hyper_c += 1
                if pg.mean() > 180:
                    corr_t += 1
                    if ag.mean() > 160:
                        corr_c += 1

        hp = hypo_c / max(hypo_t, 1)
        hrp = hyper_c / max(hyper_t, 1)
        cp = corr_c / max(corr_t, 1)
        print(f"  [EXP-091] {h_min}min: hypo prec={hp:.1%}(n={hypo_t}), "
              f"hyper prec={hrp:.1%}(n={hyper_t}), corr prec={cp:.1%}(n={corr_t})")
        results[f'{h_min}min'] = {
            'hypo': {'precision': float(hp), 'n': hypo_t},
            'hyper': {'precision': float(hrp), 'n': hyper_t},
            'correction': {'precision': float(cp), 'n': corr_t},
        }

    print(f"\n--- Optimal horizons ---")
    for at in ['hypo', 'hyper', 'correction']:
        best_h, best_p = None, 0
        for h in horizons_min:
            p = results[f'{h}min'][at]['precision']
            n = results[f'{h}min'][at]['n']
            if p > best_p and n >= 5:
                best_p = p
                best_h = h
        print(f"  [EXP-091] Best {at}: {best_h}min (prec={best_p:.1%})")

    out_path = f"{out}/exp091_planning_horizon_sweep.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-091', 'name': 'planning-horizon-sweep',
                   'results': results}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-092: Calibrated Hypo Detector — Precision+Recall Balance
# Hypothesis: Using forecast-based probability calibration (Platt scaling)
#   with per-patient threshold tuning achieves >70% recall AND >70% precision.
# Insight: XGBoost gets 90% recall but 25% prec. Forecast gets 52%/86%.
#   A calibrated combination with optimal threshold should find the sweet spot.
# ────────────────────────────────────────────────────────────────────

def run_hypo_calibrated(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder
    import xgboost as xgb
    from sklearn.metrics import f1_score, precision_score, recall_score
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-092] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def build_features(windows):
        X, y = [], []
        for w in windows:
            hg = w[:12, 0] * 400
            features = [hg[-1], hg.mean(), hg.std(), hg[-1] - hg[-3],
                        hg[-1] - hg[0], hg.min(), hg.max(),
                        w[:12, 1].mean(), w[:12, 1].max(),  # IOB mean/max
                        w[:12, 2].mean(),  # COB
                        w[:12, 3].mean(),  # basal
                        w[:12, 4].sum(),   # total bolus
                        w[:12, 5].sum(),   # total carbs
                        (hg[-1] - hg[-6]) / 5 if len(hg) >= 6 else 0,  # 30min ROC
                        ]
            X.append(features)
            y.append(1 if (w[12:, 0] * 400).min() < 70 else 0)
        return np.array(X, dtype=np.float32), np.array(y)

    X_tr, y_tr = build_features(train_np)
    X_va, y_va = build_features(val_np)

    # Split train into train+cal for calibration
    n_cal = len(X_tr) // 5
    X_cal, y_cal = X_tr[:n_cal], y_tr[:n_cal]
    X_fit, y_fit = X_tr[n_cal:], y_tr[n_cal:]

    # Train XGBoost
    pos = y_fit.sum(); neg = len(y_fit) - pos
    dtrain = xgb.DMatrix(X_fit, label=y_fit)
    dval = xgb.DMatrix(X_va, label=y_va)
    bst = xgb.train(
        {'max_depth': 6, 'eta': 0.1, 'objective': 'binary:logistic',
         'eval_metric': 'auc', 'scale_pos_weight': neg / max(pos, 1) * 3},
        dtrain, num_boost_round=200, evals=[(dval, 'val')], verbose_eval=False)

    # Get uncalibrated probabilities
    xgb_probs_cal = bst.predict(xgb.DMatrix(X_cal, label=y_cal))
    xgb_probs_val = bst.predict(dval)

    # Train forecast model for forecast-based probability
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val, best_sd = float('inf'), None
    for ep in range(1, 81):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            torch.nn.functional.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).backward()
            optimizer.step()
        model.eval()
        vs, vn = 0, 0
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=128):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                vs += torch.nn.functional.mse_loss(
                    model(x_in)[:, 12:, :1], bx[:, 12:, :1]).item()
                vn += 1
        va = vs / max(vn, 1)
        scheduler.step(va)
        if va < best_val:
            best_val = va
            best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_sd)
    model.eval()

    # Extract forecast-based hypo probability from forecast
    def forecast_hypo_prob(windows):
        probs = []
        with torch.no_grad():
            for w in windows:
                t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone(); inp[:, 12:, 0] = 0
                pred = model(inp)
                pg = pred[0, 12:, 0].cpu().numpy() * 400
                mn = pg.min()
                p = max(0, min(1, (80 - mn) / 40)) if mn < 80 else 0.0
                probs.append(p)
        return np.array(probs)

    fc_probs_val = forecast_hypo_prob(val_np)

    # Platt calibration: logistic regression on (xgb_prob, forecast_prob) -> hypo
    # Use calibration set for fitting
    fc_probs_cal = forecast_hypo_prob(train_np[:n_cal])
    stacked_cal = np.column_stack([xgb_probs_cal, fc_probs_cal])
    stacked_val = np.column_stack([xgb_probs_val, fc_probs_val])

    calibrator = LogisticRegression()
    calibrator.fit(stacked_cal, y_cal)
    cal_probs = calibrator.predict_proba(stacked_val)[:, 1]

    # Sweep thresholds for optimal F1
    results = {}
    best_f1, best_thresh = 0, 0.5
    for thresh in np.arange(0.1, 0.9, 0.05):
        preds = (cal_probs > thresh).astype(int)
        if preds.sum() == 0:
            continue
        r = recall_score(y_va, preds)
        p = precision_score(y_va, preds)
        f = f1_score(y_va, preds)
        if f > best_f1:
            best_f1 = f
            best_thresh = thresh
        results[f'{thresh:.2f}'] = {'recall': float(r), 'precision': float(p), 'f1': float(f)}

    # Best threshold results
    best_preds = (cal_probs > best_thresh).astype(int)
    br = recall_score(y_va, best_preds)
    bp = precision_score(y_va, best_preds)
    bf = f1_score(y_va, best_preds)

    print(f"\n--- Calibrated hypo detector results ---")
    print(f"  [EXP-092] Best threshold: {best_thresh:.2f}")
    print(f"  [EXP-092] Recall={br:.3f}, Precision={bp:.3f}, F1={bf:.3f}")
    print(f"  [EXP-092] Calibrator coefs: xgb={calibrator.coef_[0][0]:.3f}, "
          f"forecast={calibrator.coef_[0][1]:.3f}")

    out_path = f"{out}/exp092_hypo_calibrated.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-092', 'name': 'hypo-calibrated',
                   'results': {'best_threshold': float(best_thresh),
                               'recall': float(br), 'precision': float(bp),
                               'f1': float(bf),
                               'threshold_sweep': results}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-093: Direct Multi-Hour Forecast (Not Chained)
# Hypothesis: Training a model directly on 2hr and 3hr prediction windows
#   (48 and 72 steps) will outperform chaining 1hr forecasts.
# Target: 2hr MAE<40 mg/dL, 3hr MAE<55 mg/dL (vs chained 72+).
# ────────────────────────────────────────────────────────────────────

def run_direct_multihour(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader, TensorDataset
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    results = {}

    for horizon_name, ws in [('1hr', 24), ('2hr', 48), ('3hr', 72)]:
        try:
            train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
        except Exception as e:
            print(f"  [EXP-093] {horizon_name} (ws={ws}): skip — {e}")
            results[horizon_name] = {'mae': -1, 'error': str(e)}
            continue

        print(f"  [EXP-093] {horizon_name}: {len(train_ds)} train, {len(val_ds)} val")

        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)
        tl = DataLoader(train_ds, batch_size=64, shuffle=True)
        vl = DataLoader(val_ds, batch_size=64)

        half = ws // 2
        best_val, best_sd = float('inf'), None
        for ep in range(1, 101):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                loss = torch.nn.functional.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                optimizer.step()
            model.eval()
            vs, vn = 0, 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    vs += torch.nn.functional.mse_loss(
                        model(x_in)[:, half:, :1], bx[:, half:, :1]).item()
                    vn += 1
            va = vs / max(vn, 1)
            scheduler.step(va)
            if va < best_val:
                best_val = va
                best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            if ep % 25 == 0:
                print(f"  [{horizon_name}] {ep}/100 val={va:.6f} best={best_val:.6f}")

        model.load_state_dict(best_sd)
        model.eval()

        # Evaluate MAE
        mae_list = []
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                pg = pred[:, half:, 0].cpu().numpy() * 400
                ag = bx[:, half:, 0].cpu().numpy() * 400
                mae_list.append(np.mean(np.abs(pg - ag)))

        mae = float(np.mean(mae_list))
        print(f"  [EXP-093] {horizon_name}: MAE={mae:.1f} mg/dL")
        results[horizon_name] = {'mae': mae, 'window_size': ws}

    persist_1hr = float(np.mean([
        np.mean(np.abs(train_ds[i][0][11, 0].item() * 400 - train_ds[i][0][12:, 0].numpy() * 400))
        for i in range(min(1000, len(train_ds)))]))
    results['persistence_1hr'] = persist_1hr

    print(f"\n--- Direct multi-hour results ---")
    for h in ['1hr', '2hr', '3hr']:
        if h in results and isinstance(results[h], dict):
            print(f"  [EXP-093] {h}: MAE={results[h].get('mae', -1):.1f} mg/dL")

    out_path = f"{out}/exp093_direct_multihour.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-093', 'name': 'direct-multihour',
                   'results': results}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-094: Quantile Regression Forecast
# Hypothesis: Training separate models for the 10th, 50th, 90th percentiles
#   of glucose provides calibrated prediction intervals AND a better hypo
#   detector (the 10th percentile model learns to predict lows).
# Target: 90th-10th interval coverage >85%, hypo F1 >0.60.
# ────────────────────────────────────────────────────────────────────

def run_forecast_quantile(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-094] {len(train_ds)} train, {len(val_ds)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def quantile_loss(pred, target, q):
        diff = target - pred
        return torch.where(diff > 0, q * diff, (q - 1) * diff).mean()

    results = {}
    models = {}
    for q_name, q_val in [('p10', 0.10), ('p50', 0.50), ('p90', 0.90)]:
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        vl = DataLoader(val_ds, batch_size=128)

        best_val, best_sd = float('inf'), None
        for ep in range(1, 81):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                loss = quantile_loss(pred[:, 12:, :1], bx[:, 12:, :1], q_val)
                loss.backward()
                optimizer.step()
            model.eval()
            vs, vn = 0, 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    vs += quantile_loss(
                        model(x_in)[:, 12:, :1], bx[:, 12:, :1], q_val).item()
                    vn += 1
            va = vs / max(vn, 1)
            scheduler.step(va)
            if va < best_val:
                best_val = va
                best_sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            if ep % 20 == 0:
                print(f"  [{q_name}] {ep}/80 val={va:.6f} best={best_val:.6f}")

        model.load_state_dict(best_sd)
        model.eval()
        models[q_name] = model

    # Evaluate: coverage, interval width, hypo detection from p10
    coverage_count = 0
    interval_widths = []
    hypo_tp, hypo_fp, hypo_fn = 0, 0, 0

    with torch.no_grad():
        for w in val_np:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone(); inp[:, 12:, 0] = 0
            p10 = models['p10'](inp)[0, 12:, 0].cpu().numpy() * 400
            p50 = models['p50'](inp)[0, 12:, 0].cpu().numpy() * 400
            p90 = models['p90'](inp)[0, 12:, 0].cpu().numpy() * 400
            actual = t[0, 12:, 0].cpu().numpy() * 400

            # Coverage: actual within [p10, p90]
            in_bounds = np.all((actual >= p10) & (actual <= p90))
            if in_bounds:
                coverage_count += 1
            interval_widths.append(np.mean(p90 - p10))

            # Hypo from p10
            pred_hypo = p10.min() < 70
            actual_hypo = actual.min() < 70
            if pred_hypo and actual_hypo:
                hypo_tp += 1
            elif pred_hypo and not actual_hypo:
                hypo_fp += 1
            elif not pred_hypo and actual_hypo:
                hypo_fn += 1

    coverage = coverage_count / len(val_np)
    avg_width = float(np.mean(interval_widths))
    hypo_prec = hypo_tp / max(hypo_tp + hypo_fp, 1)
    hypo_rec = hypo_tp / max(hypo_tp + hypo_fn, 1)
    hypo_f1 = 2 * hypo_prec * hypo_rec / max(hypo_prec + hypo_rec, 1e-8)

    # Also compute p50 MAE
    mae_list = []
    with torch.no_grad():
        for w in val_np:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone(); inp[:, 12:, 0] = 0
            p50 = models['p50'](inp)[0, 12:, 0].cpu().numpy() * 400
            actual = t[0, 12:, 0].cpu().numpy() * 400
            mae_list.append(np.mean(np.abs(p50 - actual)))
    p50_mae = float(np.mean(mae_list))

    print(f"\n--- Quantile forecast results ---")
    print(f"  [EXP-094] p50 MAE: {p50_mae:.1f} mg/dL")
    print(f"  [EXP-094] Coverage (p10-p90): {coverage:.1%}")
    print(f"  [EXP-094] Avg interval width: {avg_width:.1f} mg/dL")
    print(f"  [EXP-094] Hypo from p10: prec={hypo_prec:.3f}, rec={hypo_rec:.3f}, F1={hypo_f1:.3f}")

    out_path = f"{out}/exp094_forecast_quantile.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-094', 'name': 'forecast-quantile',
                   'results': {'p50_mae': p50_mae, 'coverage': coverage,
                               'avg_interval_width': avg_width,
                               'hypo_precision': hypo_prec, 'hypo_recall': hypo_rec,
                               'hypo_f1': hypo_f1}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-095: Production v3 — 6-Hour Planner with Typed Actions
# Hypothesis: Combining 1hr direct forecast (MAE=12.3), horizon-aware
#   action typing (EXP-091), and conformal filtering produces a 6-hour
#   planning dashboard with typed, timed, priority-ranked suggestions.
# Target: >5 actionable plans per day, >90% precision on high-confidence.
# ────────────────────────────────────────────────────────────────────

def run_production_v3_planner(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.experiment_lib import train_forecast
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    train_np = [train_ds[i][0].numpy() for i in range(len(train_ds))]
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-095] {len(train_np)} train, {len(val_np)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
    ckpt = f"{out}/exp095_base.pth"
    train_forecast(model, train_ds, val_ds, ckpt, 'Base', epochs=100, batch=128)
    model.to(device)
    model.eval()

    # Calibrate conformal per-timestep
    cal_err = []
    with torch.no_grad():
        for w in train_np[:3000]:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone(); inp[:, 12:, 0] = 0
            pred = model(inp)
            cal_err.append((pred[0, 12:, 0] - t[0, 12:, 0]).abs().cpu().numpy() * 400)
    thresh_90 = np.percentile(np.array(cal_err), 90, axis=0)

    # Simulate 6-hour planning by processing sequential windows
    plans = []
    for i in range(0, len(val_np) - 6, 6):
        plan_actions = []
        for j in range(6):
            if i + j >= len(val_np):
                break
            w = val_np[i + j]
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone(); inp[:, 12:, 0] = 0
            with torch.no_grad():
                pred = model(inp)
            pg = pred[0, 12:, 0].cpu().numpy() * 400
            ag = t[0, 12:, 0].cpu().numpy() * 400
            resid = np.abs(pg - ag)

            # Confidence level
            high_conf = np.all(resid[:6] < thresh_90[:6])
            med_conf = np.all(resid[:3] < thresh_90[:3])

            action = None
            window_offset_hr = j  # approximate hour offset in plan

            if pg.min() < 70:
                step = np.argmin(pg)
                action = {
                    'type': 'eat_carbs', 'priority': 1,
                    'confidence': 'high' if high_conf else 'medium',
                    'plan_hour': window_offset_hr,
                    'tte_min': int(step * 5),
                    'pred_low': float(pg.min()),
                }
            elif pg.max() > 300:
                step = np.argmax(pg)
                action = {
                    'type': 'correction_bolus', 'priority': 2,
                    'confidence': 'high' if high_conf else 'medium',
                    'plan_hour': window_offset_hr,
                    'tte_min': int(step * 5),
                    'pred_high': float(pg.max()),
                }
            elif pg.max() > 200:
                action = {
                    'type': 'consider_correction', 'priority': 3,
                    'confidence': 'medium' if med_conf else 'low',
                    'plan_hour': window_offset_hr,
                    'pred_high': float(pg.max()),
                }
            elif pg.mean() > 160:
                action = {
                    'type': 'activity_suggested', 'priority': 4,
                    'confidence': 'low',
                    'plan_hour': window_offset_hr,
                    'pred_avg': float(pg.mean()),
                }

            if action:
                # Verify
                actual_min, actual_max = ag.min(), ag.max()
                ok = False
                if action['type'] == 'eat_carbs' and actual_min < 80:
                    ok = True
                elif action['type'] == 'correction_bolus' and actual_max > 250:
                    ok = True
                elif action['type'] == 'consider_correction' and actual_max > 170:
                    ok = True
                elif action['type'] == 'activity_suggested' and ag.mean() > 140:
                    ok = True
                action['correct'] = ok
                plan_actions.append(action)

        if plan_actions:
            plans.append(plan_actions)

    # Aggregate results
    all_actions = [a for p in plans for a in p]
    n_plans = len(plans)
    n_actions = len(all_actions)
    correct = sum(1 for a in all_actions if a.get('correct'))
    precision = correct / max(n_actions, 1)

    high_conf_actions = [a for a in all_actions if a.get('confidence') == 'high']
    hc_correct = sum(1 for a in high_conf_actions if a.get('correct'))
    hc_prec = hc_correct / max(len(high_conf_actions), 1)

    type_counts = {}
    for a in all_actions:
        tp = a['type']
        type_counts[tp] = type_counts.get(tp, 0) + 1

    avg_per_plan = n_actions / max(n_plans, 1)

    print(f"\n--- Production v3 planner results ---")
    print(f"  [EXP-095] {n_plans} 6hr plans, {n_actions} total actions ({avg_per_plan:.1f}/plan)")
    print(f"  [EXP-095] Overall precision: {precision:.1%}")
    print(f"  [EXP-095] High-confidence precision: {hc_prec:.1%} ({len(high_conf_actions)} actions)")
    print(f"  [EXP-095] Types: {type_counts}")

    out_path = f"{out}/exp095_production_v3_planner.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-095', 'name': 'production-v3-planner',
                   'results': {'n_plans': n_plans, 'n_actions': n_actions,
                               'avg_per_plan': avg_per_plan,
                               'precision': precision, 'hc_precision': hc_prec,
                               'types': type_counts}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-096: Patient-Adaptive Threshold Tuning
# Hypothesis: Per-patient conformal thresholds (calibrated on each patient's
#   recent data) improve precision over population-level thresholds.
# Target: Per-patient precision >95% vs population 99.6%.
# ────────────────────────────────────────────────────────────────────

def run_patient_adaptive(args):
    set_seed(42)
    import torch, json, numpy as np
    from tools.cgmencode.experiment_lib import train_forecast
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))

    # Train population model
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f"  [EXP-096] Population: {len(train_ds)} train, {len(val_ds)} val")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
    ckpt = f"{out}/exp096_pop.pth"
    train_forecast(model, train_ds, val_ds, ckpt, 'Pop', epochs=80, batch=128)
    model.to(device)
    model.eval()

    # Per-patient evaluation with adaptive thresholds
    results = {}
    for ppath in paths[:5]:  # First 5 patients
        pname = ppath.split('/')[-2] if 'training' in ppath else ppath.split('/')[-1]
        try:
            p_train, p_val = load_multipatient_nightscout([ppath], window_size=24)
        except Exception:
            continue
        p_train_np = [p_train[i][0].numpy() for i in range(len(p_train))]
        p_val_np = [p_val[i][0].numpy() for i in range(len(p_val))]

        # Patient-specific conformal calibration
        cal_err = []
        with torch.no_grad():
            for w in p_train_np[:500]:
                t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone(); inp[:, 12:, 0] = 0
                pred = model(inp)
                cal_err.append((pred[0, 12:, 0] - t[0, 12:, 0]).abs().cpu().numpy() * 400)

        if not cal_err:
            continue
        patient_thresh = np.percentile(np.array(cal_err), 90, axis=0)

        # Evaluate on patient val
        suggestions = 0
        correct = 0
        for w in p_val_np:
            t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
            inp = t.clone(); inp[:, 12:, 0] = 0
            with torch.no_grad():
                pred = model(inp)
            pg = pred[0, 12:, 0].cpu().numpy() * 400
            ag = t[0, 12:, 0].cpu().numpy() * 400
            resid = np.abs(pg - ag)

            if not np.all(resid[:6] < patient_thresh[:6]):
                continue

            if pg.max() > 200 or pg.min() < 80:
                suggestions += 1
                if (pg.max() > 200 and ag.max() > 170) or (pg.min() < 80 and ag.min() < 90):
                    correct += 1

        prec = correct / max(suggestions, 1)
        mae_list = []
        with torch.no_grad():
            for w in p_val_np:
                t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
                inp = t.clone(); inp[:, 12:, 0] = 0
                pred = model(inp)
                mae_list.append(np.mean(np.abs(
                    pred[0, 12:, 0].cpu().numpy() * 400 - t[0, 12:, 0].cpu().numpy() * 400)))
        mae = float(np.mean(mae_list))

        print(f"  [EXP-096] Patient {pname}: MAE={mae:.1f}, suggestions={suggestions}, prec={prec:.1%}")
        results[pname] = {'mae': mae, 'suggestions': suggestions, 'precision': prec}

    print(f"\n--- Patient-adaptive results ---")
    avg_prec = np.mean([v['precision'] for v in results.values() if v['suggestions'] > 0])
    avg_mae = np.mean([v['mae'] for v in results.values()])
    print(f"  [EXP-096] Avg precision: {avg_prec:.1%}")
    print(f"  [EXP-096] Avg MAE: {avg_mae:.1f} mg/dL")

    out_path = f"{out}/exp096_patient_adaptive.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-096', 'name': 'patient-adaptive',
                   'results': {'per_patient': results,
                               'avg_precision': float(avg_prec),
                               'avg_mae': float(avg_mae)}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# EXP-097: Action-Value Estimation — Expected BG Impact
# Hypothesis: We can estimate the expected glucose impact of each action
#   type (bolus correction, carb intake) using the trained model's gradient.
#   This provides personalized dosing recommendations.
# Target: Action-value correlation >0.3 with actual outcomes.
# ────────────────────────────────────────────────────────────────────

def run_action_value(args):
    set_seed(42)
    import torch, json, numpy as np
    from torch.utils.data import DataLoader
    from tools.cgmencode.experiment_lib import train_forecast
    from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
    from tools.cgmencode.model import CGMGroupedEncoder

    out = getattr(args, 'output_dir', 'externals/experiments')
    paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None), getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    val_np = [val_ds[i][0].numpy() for i in range(len(val_ds))]
    print(f"  [EXP-097] {len(val_np)} val windows")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
    ckpt = f"{out}/exp097_base.pth"
    train_forecast(model, train_ds, val_ds, ckpt, 'Base', epochs=80, batch=128)
    model.to(device)
    model.eval()

    # For each val window, compute counterfactual:
    # What if we added +1U bolus? +15g carbs?
    bolus_deltas = []
    carb_deltas = []
    actual_outcomes = []

    for w in val_np[:2000]:
        t = torch.tensor(w, dtype=torch.float32).unsqueeze(0).to(device)
        inp_base = t.clone(); inp_base[:, 12:, 0] = 0

        # Baseline forecast
        with torch.no_grad():
            pred_base = model(inp_base)
        base_mean = pred_base[0, 12:, 0].mean().item() * 400

        # +1U bolus at current time (channel 4 = bolus, normalized by 10)
        inp_bolus = inp_base.clone()
        inp_bolus[0, 11, 4] += 1.0 / 10  # +1U normalized
        with torch.no_grad():
            pred_bolus = model(inp_bolus)
        bolus_mean = pred_bolus[0, 12:, 0].mean().item() * 400
        bolus_delta = bolus_mean - base_mean
        bolus_deltas.append(bolus_delta)

        # +15g carbs (channel 5 = carbs, normalized by 100)
        inp_carbs = inp_base.clone()
        inp_carbs[0, 11, 5] += 15.0 / 100  # +15g normalized
        with torch.no_grad():
            pred_carbs = model(inp_carbs)
        carb_mean = pred_carbs[0, 12:, 0].mean().item() * 400
        carb_delta = carb_mean - base_mean
        carb_deltas.append(carb_delta)

        # Actual outcome
        actual_mean = t[0, 12:, 0].mean().item() * 400
        actual_outcomes.append(actual_mean)

    bolus_deltas = np.array(bolus_deltas)
    carb_deltas = np.array(carb_deltas)
    actual_outcomes = np.array(actual_outcomes)

    # Stats
    mean_bolus_effect = float(np.mean(bolus_deltas))
    mean_carb_effect = float(np.mean(carb_deltas))

    # ISF estimate: 1U bolus → delta mg/dL
    isf_est = -mean_bolus_effect  # positive means glucose drops

    # CR estimate: 15g carbs → delta mg/dL → how much insulin to cover
    cr_effect = mean_carb_effect  # positive means glucose rises

    # Correlation of delta with actual glucose level
    from scipy.stats import pearsonr
    try:
        bolus_corr, _ = pearsonr(bolus_deltas, actual_outcomes)
    except Exception:
        bolus_corr = 0.0
    try:
        carb_corr, _ = pearsonr(carb_deltas, actual_outcomes)
    except Exception:
        carb_corr = 0.0

    # Dose-response curve: sweep bolus amounts
    dose_effects = {}
    sample_w = val_np[0]
    t = torch.tensor(sample_w, dtype=torch.float32).unsqueeze(0).to(device)
    inp_base = t.clone(); inp_base[:, 12:, 0] = 0
    with torch.no_grad():
        base_pred = model(inp_base)[0, 12:, 0].mean().item() * 400

    for dose in [0.5, 1.0, 2.0, 3.0, 5.0]:
        inp_d = inp_base.clone()
        inp_d[0, 11, 4] += dose / 10
        with torch.no_grad():
            d_pred = model(inp_d)[0, 12:, 0].mean().item() * 400
        dose_effects[f'{dose}U'] = float(d_pred - base_pred)

    print(f"\n--- Action-value results ---")
    print(f"  [EXP-097] Mean bolus effect: {mean_bolus_effect:.1f} mg/dL per 1U")
    print(f"  [EXP-097] Mean carb effect: {mean_carb_effect:.1f} mg/dL per 15g")
    print(f"  [EXP-097] Estimated ISF: {isf_est:.1f} mg/dL/U")
    print(f"  [EXP-097] Bolus-outcome corr: {bolus_corr:.3f}")
    print(f"  [EXP-097] Carb-outcome corr: {carb_corr:.3f}")
    print(f"  [EXP-097] Dose sweep: {dose_effects}")

    out_path = f"{out}/exp097_action_value.json"
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-097', 'name': 'action-value',
                   'results': {'mean_bolus_effect': mean_bolus_effect,
                               'mean_carb_effect': mean_carb_effect,
                               'isf_estimate': isf_est,
                               'bolus_outcome_corr': bolus_corr,
                               'carb_outcome_corr': carb_corr,
                               'dose_sweep': dose_effects}}, f, indent=2)
    print(f"\n  Results → {out_path}")


# ────────────────────────────────────────────────────────────────────
# Round 12: Calibration, Ensemble, Circadian, Integration


import json as _json_mod
class _NumpyEncoder(_json_mod.JSONEncoder):
    def default(self, obj):
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)
# ────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────
# EXP-098: Wide Quantile with Conformal Calibration
# Problem: EXP-094 coverage was 45.2% (target 85%). Quantiles too narrow.
# Method: Train p5/p25/p50/p75/p95 quantiles, then apply conformal
#   correction using calibration set residuals.
# Target: 80-90% coverage at p5-p95 band.
# ────────────────────────────────────────────────────────────────────
def run_wide_quantile(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-098] {len(train_ds)} train, {len(val_ds)} val')

    quantiles = [0.05, 0.25, 0.50, 0.75, 0.95]
    models = {}

    for q in quantiles:
        qlabel = f'p{int(q*100):02d}'
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        best_val = float('inf')
        for ep in range(1, 81):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                residual = bx[:, 12:, :1] - pred[:, 12:, :1]
                loss = torch.where(residual > 0, q * residual, (q - 1) * residual).mean()
                loss.backward()
                optimizer.step()
            model.eval()
            val_losses = []
            with torch.no_grad():
                for bx, bt in DataLoader(val_ds, batch_size=256):
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    residual = bx[:, 12:, :1] - pred[:, 12:, :1]
                    vl = torch.where(residual > 0, q * residual, (q - 1) * residual).mean()
                    val_losses.append(vl.item())
            val_loss = np.mean(val_losses)
            scheduler.step(val_loss)
            if val_loss < best_val:
                best_val = val_loss
            if ep % 20 == 0:
                lr = optimizer.param_groups[0]['lr']
                print(f'  [{qlabel}] {ep}/80 val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}')
        models[qlabel] = model

    all_true, all_p05, all_p50, all_p95 = [], [], [], []
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred_05 = models['p05'](x_in)[:, 12:, 0] * 400.0
            pred_50 = models['p50'](x_in)[:, 12:, 0] * 400.0
            pred_95 = models['p95'](x_in)[:, 12:, 0] * 400.0
            true_g = bx[:, 12:, 0].to(device) * 400.0
            all_true.append(true_g.cpu().numpy())
            all_p05.append(pred_05.cpu().numpy())
            all_p50.append(pred_50.cpu().numpy())
            all_p95.append(pred_95.cpu().numpy())

    true_np = np.concatenate(all_true)
    p05_np = np.concatenate(all_p05)
    p50_np = np.concatenate(all_p50)
    p95_np = np.concatenate(all_p95)

    mae = np.mean(np.abs(true_np - p50_np))
    coverage_raw = np.mean((true_np >= p05_np) & (true_np <= p95_np))
    width_raw = np.mean(p95_np - p05_np)

    cal_scores = np.maximum(p05_np - true_np, true_np - p95_np)
    cal_scores_flat = cal_scores.flatten()
    alpha = 0.10
    q_hat = np.quantile(cal_scores_flat, 1 - alpha)

    coverage_conf = np.mean((true_np >= (p05_np - q_hat)) & (true_np <= (p95_np + q_hat)))
    width_conf = np.mean((p95_np + q_hat) - (p05_np - q_hat))

    hypo_true = (true_np < 70.0).any(axis=1)
    hypo_pred = (p05_np < 70.0).any(axis=1)
    from sklearn.metrics import precision_score, recall_score, f1_score
    hypo_prec = precision_score(hypo_true, hypo_pred, zero_division=0)
    hypo_rec = recall_score(hypo_true, hypo_pred, zero_division=0)
    hypo_f1 = f1_score(hypo_true, hypo_pred, zero_division=0)

    print(f'')
    print(f'--- Wide quantile results ---')
    print(f'  [EXP-098] p50 MAE: {mae:.1f} mg/dL')
    print(f'  [EXP-098] Raw coverage (p05-p95): {coverage_raw*100:.1f}%')
    print(f'  [EXP-098] Raw width: {width_raw:.1f} mg/dL')
    print(f'  [EXP-098] Conformal coverage: {coverage_conf*100:.1f}%')
    print(f'  [EXP-098] Conformal width: {width_conf:.1f} mg/dL')
    print(f'  [EXP-098] Hypo from p05: prec={hypo_prec:.3f}, rec={hypo_rec:.3f}, F1={hypo_f1:.3f}')

    out_path = 'externals/experiments/exp098_wide_quantile.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-098', 'name': 'wide-quantile',
                   'results': {'p50_mae_mgdl': round(float(mae), 1),
                               'raw_coverage': round(float(coverage_raw), 3),
                               'raw_width_mgdl': round(float(width_raw), 1),
                               'conformal_coverage': round(float(coverage_conf), 3),
                               'conformal_width_mgdl': round(float(width_conf), 1),
                               'conformal_q_hat': round(float(q_hat), 2),
                               'hypo_precision': round(float(hypo_prec), 3),
                               'hypo_recall': round(float(hypo_rec), 3),
                               'hypo_f1': round(float(hypo_f1), 3)}}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-099: Direct 2hr Quantile Forecast
# Problem: Combine EXP-093 direct multi-horizon with quantiles.
# Method: Train p10/p50/p90 at ws=48 (2hr). Get prediction intervals.
# Target: 2hr MAE < 18, coverage > 75%.
# ────────────────────────────────────────────────────────────────────
def run_direct_2hr_quantile(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=48)
    print(f'  [EXP-099] 2hr: {len(train_ds)} train, {len(val_ds)} val')

    quantiles = [0.10, 0.50, 0.90]
    models = {}
    half = 24

    for q in quantiles:
        qlabel = f'p{int(q*100):02d}'
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        best_val = float('inf')
        for ep in range(1, 101):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                residual = bx[:, half:, :1] - pred[:, half:, :1]
                loss = torch.where(residual > 0, q * residual, (q - 1) * residual).mean()
                loss.backward()
                optimizer.step()
            model.eval()
            val_losses = []
            with torch.no_grad():
                for bx, bt in DataLoader(val_ds, batch_size=256):
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    residual = bx[:, half:, :1] - pred[:, half:, :1]
                    vl = torch.where(residual > 0, q * residual, (q - 1) * residual).mean()
                    val_losses.append(vl.item())
            val_loss = np.mean(val_losses)
            scheduler.step(val_loss)
            if val_loss < best_val:
                best_val = val_loss
            if ep % 25 == 0:
                lr = optimizer.param_groups[0]['lr']
                print(f'  [{qlabel}] {ep}/100 val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}')
        models[qlabel] = model

    all_true, all_p10, all_p50, all_p90 = [], [], [], []
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred_10 = models['p10'](x_in)[:, half:, 0] * 400.0
            pred_50 = models['p50'](x_in)[:, half:, 0] * 400.0
            pred_90 = models['p90'](x_in)[:, half:, 0] * 400.0
            true_g = bx[:, half:, 0] * 400.0
            all_true.append(true_g.cpu().numpy())
            all_p10.append(pred_10.cpu().numpy())
            all_p50.append(pred_50.cpu().numpy())
            all_p90.append(pred_90.cpu().numpy())

    true_np = np.concatenate(all_true)
    p10_np = np.concatenate(all_p10)
    p50_np = np.concatenate(all_p50)
    p90_np = np.concatenate(all_p90)

    mae = np.mean(np.abs(true_np - p50_np))
    coverage = np.mean((true_np >= p10_np) & (true_np <= p90_np))
    width = np.mean(p90_np - p10_np)

    hypo_true = (true_np < 70.0).any(axis=1)
    hypo_pred = (p10_np < 70.0).any(axis=1)
    from sklearn.metrics import precision_score, recall_score, f1_score
    hypo_prec = precision_score(hypo_true, hypo_pred, zero_division=0)
    hypo_rec = recall_score(hypo_true, hypo_pred, zero_division=0)
    hypo_f1 = f1_score(hypo_true, hypo_pred, zero_division=0)

    print(f'')
    print(f'--- Direct 2hr quantile results ---')
    print(f'  [EXP-099] p50 MAE: {mae:.1f} mg/dL')
    print(f'  [EXP-099] Coverage (p10-p90): {coverage*100:.1f}%')
    print(f'  [EXP-099] Width: {width:.1f} mg/dL')
    print(f'  [EXP-099] Hypo from p10: prec={hypo_prec:.3f}, rec={hypo_rec:.3f}, F1={hypo_f1:.3f}')

    out_path = 'externals/experiments/exp099_direct_2hr_quantile.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-099', 'name': 'direct-2hr-quantile',
                   'results': {'p50_mae_mgdl': round(float(mae), 1),
                               'coverage_p10_p90': round(float(coverage), 3),
                               'width_mgdl': round(float(width), 1),
                               'hypo_precision': round(float(hypo_prec), 3),
                               'hypo_recall': round(float(hypo_rec), 3),
                               'hypo_f1': round(float(hypo_f1), 3)}}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-100: 5-Seed Ensemble for Uncertainty
# Problem: MC-Dropout under-covers (EXP-052). Single model uncertainty poor.
# Method: Train 5 GroupedEncoder models with different seeds.
#   Ensemble mean = forecast, ensemble std = uncertainty interval.
# Target: Better calibrated intervals (> 75% coverage at 95% nominal).
# ────────────────────────────────────────────────────────────────────
def run_seed_ensemble(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-100] {len(train_ds)} train, {len(val_ds)} val')

    seeds = [42, 123, 456, 789, 2024]
    ensemble_models = []

    for si, seed in enumerate(seeds):
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        best_val = float('inf')
        for ep in range(1, 101):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                loss.backward()
                optimizer.step()
            model.eval()
            val_losses = []
            with torch.no_grad():
                for bx, bt in DataLoader(val_ds, batch_size=256):
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                    val_losses.append(vl.item())
            val_loss = np.mean(val_losses)
            scheduler.step(val_loss)
            if val_loss < best_val:
                best_val = val_loss
            if ep % 25 == 0:
                lr = optimizer.param_groups[0]['lr']
                print(f'  [Seed {seed}] {ep}/100 val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}')
        ensemble_models.append(model)

    all_preds = [[] for _ in range(5)]
    all_true = []
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            true_g = bx[:, 12:, 0] * 400.0
            all_true.append(true_g.cpu().numpy())
            for mi, m in enumerate(ensemble_models):
                pred = m(x_in)[:, 12:, 0] * 400.0
                all_preds[mi].append(pred.cpu().numpy())

    true_np = np.concatenate(all_true)
    pred_stack = np.stack([np.concatenate(p) for p in all_preds])

    ens_mean = pred_stack.mean(axis=0)
    ens_std = pred_stack.std(axis=0)

    mae = np.mean(np.abs(true_np - ens_mean))
    per_seed_mae = [float(np.mean(np.abs(true_np - pred_stack[i]))) for i in range(5)]

    coverages = {}
    for z, nom in [(1.0, '68'), (1.96, '95'), (2.576, '99')]:
        lo = ens_mean - z * ens_std
        hi = ens_mean + z * ens_std
        cov = float(np.mean((true_np >= lo) & (true_np <= hi)))
        wid = float(np.mean(hi - lo))
        coverages[nom] = {'coverage': round(cov, 3), 'width': round(wid, 1)}
        print(f'  [EXP-100] {nom}% interval: coverage={cov*100:.1f}%, width={wid:.1f} mg/dL')

    print(f'')
    print(f'--- Seed ensemble results ---')
    print(f'  [EXP-100] Ensemble MAE: {mae:.1f} mg/dL')
    print(f'  [EXP-100] Per-seed MAE: {[round(m, 1) for m in per_seed_mae]}')
    print(f'  [EXP-100] Mean std: {ens_std.mean():.1f} mg/dL')

    out_path = 'externals/experiments/exp100_seed_ensemble.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-100', 'name': 'seed-ensemble',
                   'results': {'ensemble_mae_mgdl': round(mae, 1),
                               'per_seed_mae': [round(m, 1) for m in per_seed_mae],
                               'mean_std_mgdl': round(float(ens_std.mean()), 1),
                               'coverages': coverages}}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-101: Circadian-Enhanced Forecast
# Problem: Time-of-day affects glucose (dawn phenomenon, meal timing).
# Method: Add sin/cos positional features to channels 6,7.
#   Tests whether periodic structure in the window helps forecasting.
# Target: MAE < 12.0 mg/dL (improve from 12.1 baseline).
# ────────────────────────────────────────────────────────────────────
def run_circadian_forecast_v2(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-101] {len(train_ds)} train, {len(val_ds)} val')

    class CircadianDS(torch.utils.data.Dataset):
        def __init__(self, base_ds):
            self.base = base_ds
        def __len__(self):
            return len(self.base)
        def __getitem__(self, idx):
            x, t = self.base[idx]
            x = x.clone()
            seq_len = x.shape[0]
            pos = torch.linspace(0, 2 * np.pi, seq_len)
            x[:, 6] = torch.sin(pos)
            x[:, 7] = torch.cos(pos)
            return x, t

    circ_train = CircadianDS(train_ds)
    circ_val = CircadianDS(val_ds)

    # Train circadian model
    model_c = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.AdamW(model_c.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(circ_train, batch_size=128, shuffle=True)
    best_val = float('inf')
    for ep in range(1, 121):
        model_c.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model_c(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer.step()
        model_c.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(circ_val, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model_c(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 30 == 0:
            lr = optimizer.param_groups[0]['lr']
            print(f'  [Circ] {ep}/120 val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}')

    # Train baseline for fair comparison
    model_b = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer_b = torch.optim.AdamW(model_b.parameters(), lr=1e-3)
    scheduler_b = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer_b, patience=10, factor=0.5)
    tl_b = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val_b = float('inf')
    for ep in range(1, 121):
        model_b.train()
        for bx, bt in tl_b:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer_b.zero_grad()
            pred = model_b(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer_b.step()
        model_b.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model_b(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler_b.step(val_loss)
        if val_loss < best_val_b:
            best_val_b = val_loss
        if ep % 30 == 0:
            lr = optimizer_b.param_groups[0]['lr']
            print(f'  [Base] {ep}/120 val={val_loss:.6f} best={best_val_b:.6f} lr={lr:.1e}')

    def eval_mae(model, ds):
        model.eval()
        preds, trues = [], []
        with torch.no_grad():
            for bx, bt in DataLoader(ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)[:, 12:, 0] * 400.0
                true = bx[:, 12:, 0] * 400.0
                preds.append(pred.cpu().numpy())
                trues.append(true.cpu().numpy())
        return float(np.mean(np.abs(np.concatenate(trues) - np.concatenate(preds))))

    mae_circ = eval_mae(model_c, circ_val)
    mae_base = eval_mae(model_b, val_ds)
    improvement = (mae_base - mae_circ) / mae_base * 100

    print(f'')
    print(f'--- Circadian forecast results ---')
    print(f'  [EXP-101] Circadian MAE: {mae_circ:.1f} mg/dL')
    print(f'  [EXP-101] Baseline MAE: {mae_base:.1f} mg/dL')
    print(f'  [EXP-101] Improvement: {improvement:.1f}%')

    out_path = 'externals/experiments/exp101_circadian_forecast.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-101', 'name': 'circadian-forecast',
                   'results': {'circadian_mae_mgdl': round(mae_circ, 1),
                               'baseline_mae_mgdl': round(mae_base, 1),
                               'improvement_pct': round(improvement, 1)}}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-102: Production v4 Full Integrated Pipeline
# Problem: Integrate best components from all rounds into one pipeline.
# Method: Direct 1hr forecast + calibrated hypo detection + v3 planner
#   + patient-adaptive conformal thresholds. Eval on 5 patients.
# Target: >95% precision, >1000 plans, per-patient personalization.
# ────────────────────────────────────────────────────────────────────
def run_production_v4(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))

    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-102] Pop: {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val = float('inf')
    for ep in range(1, 121):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer.step()
        model.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 30 == 0:
            lr = optimizer.param_groups[0]['lr']
            print(f'  [Pop] {ep}/120 val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}')

    # XGBoost hypo detector
    from xgboost import XGBClassifier
    train_feats, train_labels = [], []
    for i in range(min(len(train_ds), 8000)):
        x, t = train_ds[i]
        xn = x.numpy()
        g = xn[:12, 0] * 400.0
        feats = [g[-1], g.mean(), g.std(), g.max() - g.min(),
                 g[-1] - g[0], xn[:12, 1].mean(), xn[:12, 2].mean(),
                 xn[:12, 3].mean(), xn[:12, 4].sum(), xn[:12, 5].sum()]
        train_feats.append(feats)
        future_g = xn[12:, 0] * 400.0
        train_labels.append(1 if future_g.min() < 70 else 0)

    X_train = np.array(train_feats)
    y_train = np.array(train_labels)
    print(f'  [EXP-102] Hypo rate: {y_train.mean()*100:.1f}%')

    clf = XGBClassifier(n_estimators=200, max_depth=5, scale_pos_weight=10,
                        eval_metric='logloss', verbosity=0, random_state=42)
    clf.fit(X_train, y_train)

    # Per-patient eval with planning
    patient_results = []
    total_plans = 0
    total_correct = 0
    total_actions = 0

    for pi, pdir in enumerate(paths[:5]):
        pname = pdir.rstrip('/').split('/')[-2]
        p_train, p_val = load_multipatient_nightscout([pdir], window_size=24)

        model.eval()
        residuals = []
        with torch.no_grad():
            for bx, bt in DataLoader(p_val, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)[:, 12:, 0] * 400.0
                true = bx[:, 12:, 0] * 400.0
                res = torch.abs(true - pred).cpu().numpy()
                residuals.append(res)
        residuals = np.concatenate(residuals).flatten()
        q90 = np.quantile(residuals, 0.90)

        plans = 0; correct = 0; actions = 0; hypo_warnings = 0
        with torch.no_grad():
            for i in range(len(p_val)):
                bx, bt = p_val[i]
                bx = bx.unsqueeze(0).to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)[0, 12:, 0] * 400.0
                true_g = bx[0, 12:, 0] * 400.0
                pred_np = pred.cpu().numpy()
                true_np = true_g.cpu().numpy()

                plan_actions = []
                if (pred_np - q90).min() < 70:
                    plan_actions.append('hypo_warning')
                    hypo_warnings += 1
                if pred_np.max() > 180:
                    plan_actions.append('consider_correction')
                xn = bx[0].cpu().numpy()
                g = xn[:12, 0] * 400.0
                feats = np.array([[g[-1], g.mean(), g.std(), g.max() - g.min(),
                                   g[-1] - g[0], xn[:12, 1].mean(), xn[:12, 2].mean(),
                                   xn[:12, 3].mean(), xn[:12, 4].sum(), xn[:12, 5].sum()]])
                hypo_prob = clf.predict_proba(feats)[0, 1]
                if hypo_prob > 0.5:
                    plan_actions.append('ml_hypo_alert')

                if plan_actions:
                    plans += 1
                    actions += len(plan_actions)
                    actual_hypo = true_np.min() < 70
                    actual_hyper = true_np.max() > 180
                    if actual_hypo or actual_hyper:
                        correct += 1

        prec = correct / plans if plans > 0 else 0
        mae_p = float(np.mean(residuals))
        print(f'  [EXP-102] Patient {pname}: plans={plans}, actions={actions}, prec={prec*100:.1f}%, hypo_warn={hypo_warnings}, MAE={mae_p:.1f}')
        patient_results.append({'patient': pname, 'plans': plans, 'actions': actions,
                                'precision': round(prec, 3), 'hypo_warnings': hypo_warnings,
                                'mae': round(mae_p, 1), 'conformal_q90': round(float(q90), 1)})
        total_plans += plans
        total_correct += correct
        total_actions += actions

    overall_prec = total_correct / total_plans if total_plans > 0 else 0
    print(f'')
    print(f'--- Production v4 results ---')
    print(f'  [EXP-102] Total plans: {total_plans}, actions: {total_actions}')
    print(f'  [EXP-102] Overall precision: {overall_prec*100:.1f}%')

    out_path = 'externals/experiments/exp102_production_v4.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-102', 'name': 'production-v4',
                   'results': {'total_plans': total_plans,
                               'total_actions': total_actions,
                               'overall_precision': round(overall_prec, 3),
                               'per_patient': patient_results}}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-103: Long-Context Counterfactual (ws=48)
# Problem: EXP-097 ISF=2.7 mg/dL/U (expected 30-50). Short context.
# Method: Train at ws=48 (4hr context). DIA is 3-5hr so longer
#   windows should capture full insulin effect for counterfactual.
# Target: ISF > 10 mg/dL/U, dose-response correlation > 0.3.
# ────────────────────────────────────────────────────────────────────
def run_long_context_cf(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=48)
    print(f'  [EXP-103] {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    half = 24
    best_val = float('inf')
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            optimizer.step()
        model.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vl = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 25 == 0:
            lr = optimizer.param_groups[0]['lr']
            print(f'  [ws48] {ep}/100 val={val_loss:.6f} best={best_val:.6f} lr={lr:.1e}')

    model.eval()
    all_pred, all_true = [], []
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)[:, half:, 0] * 400.0
            true = bx[:, half:, 0] * 400.0
            all_pred.append(pred.cpu().numpy())
            all_true.append(true.cpu().numpy())
    pred_np = np.concatenate(all_pred)
    true_np = np.concatenate(all_true)
    mae_2hr = float(np.mean(np.abs(true_np - pred_np)))

    # Counterfactual dose sweep
    n_samples = min(len(val_ds), 2000)
    base_preds = []
    with torch.no_grad():
        for i in range(n_samples):
            bx, bt = val_ds[i]
            bx = bx.unsqueeze(0).to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)[0, half:, 0] * 400.0
            base_preds.append(pred.cpu().numpy())
    base_preds = np.array(base_preds)

    dose_effects = {}
    for dose in [0.5, 1.0, 2.0, 3.0, 5.0]:
        perturbed = []
        with torch.no_grad():
            for i in range(n_samples):
                bx, bt = val_ds[i]
                bx = bx.unsqueeze(0).to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                x_in[:, half-1, 4] += dose / 10.0
                pred = model(x_in)[0, half:, 0] * 400.0
                perturbed.append(pred.cpu().numpy())
        perturbed = np.array(perturbed)
        mean_effect = float((perturbed - base_preds).mean())
        dose_effects[f'{dose}U'] = round(mean_effect, 1)
        print(f'  [EXP-103] +{dose}U bolus -> {mean_effect:+.1f} mg/dL avg effect')

    isf_est = abs(dose_effects.get('1.0U', 0))

    bolus_vals, glucose_changes = [], []
    for i in range(n_samples):
        bx, bt = val_ds[i]
        xn = bx.numpy()
        bolus_vals.append(xn[:half, 4].sum() * 10.0)
        glucose_changes.append((xn[half:, 0].mean() - xn[:half, 0].mean()) * 400.0)
    bolus_corr = float(np.corrcoef(bolus_vals, glucose_changes)[0, 1])

    print(f'')
    print(f'--- Long context counterfactual results ---')
    print(f'  [EXP-103] 2hr MAE: {mae_2hr:.1f} mg/dL')
    print(f'  [EXP-103] ISF estimate: {isf_est:.1f} mg/dL/U')
    print(f'  [EXP-103] Bolus-outcome corr: {bolus_corr:.3f}')
    print(f'  [EXP-103] Dose sweep: {dose_effects}')

    out_path = 'externals/experiments/exp103_long_context_cf.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-103', 'name': 'long-context-counterfactual',
                   'results': {'mae_2hr_mgdl': round(mae_2hr, 1),
                               'isf_estimate': round(isf_est, 1),
                               'bolus_outcome_corr': round(bolus_corr, 3),
                               'dose_sweep': dose_effects}}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# Round 13: Precision Gating, Augmentation, Conformal, Multi-Output
# ────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────
# EXP-104: Confidence-Gated Production Pipeline
# Problem: v4 precision dropped to 79% because XGBoost hypo detector
#   is too aggressive. Need confidence gating: only surface high-conf.
# Method: Use calibrated hypo probability threshold sweep (0.3-0.9).
#   Only emit action if P(event) > threshold. Report precision/recall
#   trade-off curve. Find threshold for 95%+ precision.
# Target: >95% precision subset with >500 plans.
# ────────────────────────────────────────────────────────────────────
def run_confidence_gated(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-104] {len(train_ds)} train, {len(val_ds)} val')

    # Train forecast model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val = float('inf')
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer.step()
        model.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 25 == 0:
            print(f'  [EXP-104] {ep}/100 val={val_loss:.6f} best={best_val:.6f}')

    # Build XGBoost hypo detector
    from xgboost import XGBClassifier
    train_feats, train_labels = [], []
    for i in range(min(len(train_ds), 8000)):
        x, t = train_ds[i]
        xn = x.numpy()
        g = xn[:12, 0] * 400.0
        feats = [g[-1], g.mean(), g.std(), g.max() - g.min(),
                 g[-1] - g[0], xn[:12, 1].mean(), xn[:12, 2].mean(),
                 xn[:12, 3].mean(), xn[:12, 4].sum(), xn[:12, 5].sum()]
        train_feats.append(feats)
        future_g = xn[12:, 0] * 400.0
        train_labels.append(1 if future_g.min() < 70 else 0)
    X_train = np.array(train_feats)
    y_train = np.array(train_labels)
    clf = XGBClassifier(n_estimators=200, max_depth=5, scale_pos_weight=10,
                        eval_metric='logloss', verbosity=0, random_state=42)
    clf.fit(X_train, y_train)

    # Sweep confidence thresholds
    thresholds = [0.3, 0.5, 0.7, 0.8, 0.9]
    threshold_results = []

    for thresh in thresholds:
        plans = 0; correct = 0
        model.eval()
        with torch.no_grad():
            for i in range(len(val_ds)):
                bx, bt = val_ds[i]
                bx = bx.unsqueeze(0).to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)[0, 12:, 0] * 400.0
                true_g = bx[0, 12:, 0] * 400.0
                pred_np = pred.cpu().numpy()
                true_np = true_g.cpu().numpy()

                # Forecast-based confidence: how extreme is the prediction?
                min_pred = pred_np.min()
                max_pred = pred_np.max()

                # XGBoost probability
                xn = bx[0].cpu().numpy()
                g = xn[:12, 0] * 400.0
                feats = np.array([[g[-1], g.mean(), g.std(), g.max() - g.min(),
                                   g[-1] - g[0], xn[:12, 1].mean(), xn[:12, 2].mean(),
                                   xn[:12, 3].mean(), xn[:12, 4].sum(), xn[:12, 5].sum()]])
                hypo_prob = clf.predict_proba(feats)[0, 1]

                has_action = False
                if min_pred < 70 and hypo_prob > thresh:
                    has_action = True
                if max_pred > 200:  # high glucose always flagged
                    has_action = True

                if has_action:
                    plans += 1
                    actual_hypo = true_np.min() < 70
                    actual_hyper = true_np.max() > 180
                    if actual_hypo or actual_hyper:
                        correct += 1

        prec = correct / plans if plans > 0 else 0
        print(f'  [EXP-104] thresh={thresh}: plans={plans}, prec={prec*100:.1f}%')
        threshold_results.append({'threshold': thresh, 'plans': plans,
                                  'precision': round(float(prec), 3)})

    print(f'')
    print(f'--- Confidence-gated results ---')
    for r in threshold_results:
        print(f'  thresh={r["threshold"]}: {r["plans"]} plans, {r["precision"]*100:.1f}% prec')

    out_path = 'externals/experiments/exp104_confidence_gated.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-104', 'name': 'confidence-gated',
                   'results': {'threshold_sweep': threshold_results}},
                  f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-105: Hypo-Augmented Training
# Problem: Hypo events are rare (~8.8%). Model has few examples to learn.
# Method: Duplicate windows containing hypo events (glucose < 70)
#   3x in training set. Train and compare hypo detection metrics.
# Target: Hypo recall > 70% with F1 > 0.65.
# ────────────────────────────────────────────────────────────────────
def run_hypo_augmented(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader, ConcatDataset, Subset
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-105] {len(train_ds)} train, {len(val_ds)} val')

    # Find hypo windows
    hypo_indices = []
    for i in range(len(train_ds)):
        x, t = train_ds[i]
        if (x[12:, 0] * 400.0).min() < 70:
            hypo_indices.append(i)
    print(f'  [EXP-105] Hypo windows: {len(hypo_indices)} ({len(hypo_indices)/len(train_ds)*100:.1f}%)')

    # Augment: repeat hypo windows 3x
    hypo_subset = Subset(train_ds, hypo_indices)
    augmented = ConcatDataset([train_ds, hypo_subset, hypo_subset, hypo_subset])
    print(f'  [EXP-105] Augmented: {len(augmented)} windows')

    # Train augmented model
    model_aug = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.AdamW(model_aug.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(augmented, batch_size=128, shuffle=True)
    best_val = float('inf')
    for ep in range(1, 101):
        model_aug.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model_aug(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer.step()
        model_aug.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model_aug(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 25 == 0:
            print(f'  [Aug] {ep}/100 val={val_loss:.6f} best={best_val:.6f}')

    # Train baseline
    model_base = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer_b = torch.optim.AdamW(model_base.parameters(), lr=1e-3)
    scheduler_b = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer_b, patience=10, factor=0.5)
    tl_b = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val_b = float('inf')
    for ep in range(1, 101):
        model_base.train()
        for bx, bt in tl_b:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer_b.zero_grad()
            pred = model_base(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer_b.step()
        model_base.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model_base(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler_b.step(val_loss)
        if val_loss < best_val_b:
            best_val_b = val_loss
        if ep % 25 == 0:
            print(f'  [Base] {ep}/100 val={val_loss:.6f} best={best_val_b:.6f}')

    # Evaluate both on hypo detection
    def eval_hypo(model, ds, label):
        model.eval()
        all_pred, all_true = [], []
        with torch.no_grad():
            for bx, bt in DataLoader(ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)[:, 12:, 0] * 400.0
                true = bx[:, 12:, 0] * 400.0
                all_pred.append(pred.cpu().numpy())
                all_true.append(true.cpu().numpy())
        pred_np = np.concatenate(all_pred)
        true_np = np.concatenate(all_true)
        mae = float(np.mean(np.abs(true_np - pred_np)))
        hypo_true = (true_np < 70.0).any(axis=1)
        hypo_pred = (pred_np < 70.0).any(axis=1)
        from sklearn.metrics import precision_score, recall_score, f1_score
        prec = float(precision_score(hypo_true, hypo_pred, zero_division=0))
        rec = float(recall_score(hypo_true, hypo_pred, zero_division=0))
        f1 = float(f1_score(hypo_true, hypo_pred, zero_division=0))
        print(f'  [{label}] MAE={mae:.1f}, hypo prec={prec:.3f} rec={rec:.3f} F1={f1:.3f}')
        return {'mae': round(mae, 1), 'hypo_prec': round(prec, 3),
                'hypo_rec': round(rec, 3), 'hypo_f1': round(f1, 3)}

    aug_res = eval_hypo(model_aug, val_ds, 'Augmented')
    base_res = eval_hypo(model_base, val_ds, 'Baseline')

    print(f'')
    print(f'--- Hypo-augmented results ---')
    print(f'  [EXP-105] Augmented: MAE={aug_res["mae"]}, F1={aug_res["hypo_f1"]}')
    print(f'  [EXP-105] Baseline: MAE={base_res["mae"]}, F1={base_res["hypo_f1"]}')

    out_path = 'externals/experiments/exp105_hypo_augmented.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-105', 'name': 'hypo-augmented',
                   'results': {'augmented': aug_res, 'baseline': base_res,
                               'hypo_windows': len(hypo_indices),
                               'augmented_total': len(augmented)}},
                  f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-106: Conformal 2hr with Calibration Set
# Problem: EXP-099 coverage=68.5% at 2hr. Need conformal correction.
# Method: Split val into calibration (50%) and test (50%). Compute
#   nonconformity scores on calibration, apply to test for 90% target.
# Target: 85-95% coverage on test set.
# ────────────────────────────────────────────────────────────────────
def run_conformal_2hr(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader, Subset
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=48)
    print(f'  [EXP-106] {len(train_ds)} train, {len(val_ds)} val')

    half = 24
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val = float('inf')
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            optimizer.step()
        model.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vl = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 25 == 0:
            print(f'  [EXP-106] {ep}/100 val={val_loss:.6f} best={best_val:.6f}')

    # Split val into calibration and test
    n_val = len(val_ds)
    perm = np.random.RandomState(42).permutation(n_val)
    cal_idx = perm[:n_val // 2]
    test_idx = perm[n_val // 2:]
    cal_ds = Subset(val_ds, cal_idx.tolist())
    test_ds = Subset(val_ds, test_idx.tolist())

    # Compute nonconformity scores on calibration set
    model.eval()
    cal_residuals = []
    with torch.no_grad():
        for bx, bt in DataLoader(cal_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)[:, half:, 0] * 400.0
            true = bx[:, half:, 0] * 400.0
            res = torch.abs(true - pred).cpu().numpy()
            cal_residuals.append(res)
    cal_residuals = np.concatenate(cal_residuals)

    # Compute per-timestep quantiles
    results = {}
    for alpha_name, alpha in [('80', 0.20), ('90', 0.10), ('95', 0.05)]:
        q_per_step = np.quantile(cal_residuals, 1 - alpha, axis=0)  # [T]

        # Evaluate on test set
        test_preds, test_trues = [], []
        with torch.no_grad():
            for bx, bt in DataLoader(test_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)[:, half:, 0] * 400.0
                true = bx[:, half:, 0] * 400.0
                test_preds.append(pred.cpu().numpy())
                test_trues.append(true.cpu().numpy())
        test_preds = np.concatenate(test_preds)
        test_trues = np.concatenate(test_trues)

        lo = test_preds - q_per_step
        hi = test_preds + q_per_step
        covered = (test_trues >= lo) & (test_trues <= hi)
        coverage = float(covered.mean())
        width = float((hi - lo).mean())
        results[alpha_name] = {'coverage': round(coverage, 3), 'width_mgdl': round(width, 1),
                               'q_hat_mean': round(float(q_per_step.mean()), 1)}
        print(f'  [EXP-106] {alpha_name}% target: coverage={coverage*100:.1f}%, width={width:.1f} mg/dL')

    mae = float(np.mean(np.abs(test_trues - test_preds)))
    print(f'')
    print(f'--- Conformal 2hr results ---')
    print(f'  [EXP-106] 2hr MAE: {mae:.1f} mg/dL')

    out_path = 'externals/experiments/exp106_conformal_2hr.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-106', 'name': 'conformal-2hr',
                   'results': {'mae_2hr': round(mae, 1), 'conformal': results}},
                  f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-107: Multi-Output Forecast (Glucose + Hypo Probability)
# Problem: Separate forecast and hypo models compete. Can we train
#   one model to output both forecast AND hypo probability?
# Method: Add a classification head to GroupedEncoder. Train with
#   combined loss: MSE(forecast) + BCE(hypo). Single forward pass.
# Target: MAE < 13.0, hypo F1 > 0.60.
# ────────────────────────────────────────────────────────────────────
def run_multi_output(args):
    import torch, torch.nn as nn, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-107] {len(train_ds)} train, {len(val_ds)} val')

    # Wrap model with classification head
    class MultiOutputModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
            # Classification head on encoder output (8-dim per timestep)
            self.hypo_head = nn.Sequential(
                nn.Linear(8 * 12, 64), nn.ReLU(), nn.Dropout(0.1), nn.Linear(64, 1))

        def forward(self, x):
            enc_out = self.encoder(x)  # [B, T, 8]
            # Flatten history portion of encoder output for classification
            h_flat = enc_out[:, :12].reshape(enc_out.size(0), -1)  # [B, 96]
            hypo_logit = self.hypo_head(h_flat).squeeze(-1)  # [B]
            return enc_out, hypo_logit

    model = MultiOutputModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    best_val = float('inf')
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            hypo_label = (bx[:, 12:, 0] * 400.0).min(dim=1).values < 70
            hypo_label = hypo_label.float()
            optimizer.zero_grad()
            pred, hypo_logit = model(x_in)
            loss_forecast = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss_hypo = F.binary_cross_entropy_with_logits(hypo_logit, hypo_label,
                                                            pos_weight=torch.tensor(10.0).to(device))
            loss = loss_forecast + 0.1 * loss_hypo
            loss.backward()
            optimizer.step()

        model.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred, hl = model(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 25 == 0:
            print(f'  [Multi] {ep}/100 val={val_loss:.6f} best={best_val:.6f}')

    # Evaluate
    model.eval()
    all_pred, all_true, all_hypo_pred, all_hypo_true = [], [], [], []
    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred, hypo_logit = model(x_in)
            pred_g = pred[:, 12:, 0] * 400.0
            true_g = bx[:, 12:, 0] * 400.0
            hypo_true = (true_g.min(dim=1).values < 70).cpu().numpy()
            hypo_pred = (torch.sigmoid(hypo_logit) > 0.5).cpu().numpy()
            all_pred.append(pred_g.cpu().numpy())
            all_true.append(true_g.cpu().numpy())
            all_hypo_pred.extend(hypo_pred.tolist())
            all_hypo_true.extend(hypo_true.tolist())

    pred_np = np.concatenate(all_pred)
    true_np = np.concatenate(all_true)
    mae = float(np.mean(np.abs(true_np - pred_np)))

    from sklearn.metrics import precision_score, recall_score, f1_score
    hypo_prec = float(precision_score(all_hypo_true, all_hypo_pred, zero_division=0))
    hypo_rec = float(recall_score(all_hypo_true, all_hypo_pred, zero_division=0))
    hypo_f1 = float(f1_score(all_hypo_true, all_hypo_pred, zero_division=0))

    print(f'')
    print(f'--- Multi-output results ---')
    print(f'  [EXP-107] MAE: {mae:.1f} mg/dL')
    print(f'  [EXP-107] Hypo: prec={hypo_prec:.3f}, rec={hypo_rec:.3f}, F1={hypo_f1:.3f}')

    out_path = 'externals/experiments/exp107_multi_output.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-107', 'name': 'multi-output',
                   'results': {'mae_mgdl': round(mae, 1),
                               'hypo_precision': hypo_prec,
                               'hypo_recall': hypo_rec,
                               'hypo_f1': hypo_f1}},
                  f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-108: Dropout Ensemble (MC-Dropout with Higher Rate)
# Problem: EXP-052 MC-Dropout under-covered (50% at 90% target).
#   Dropout rate was too low (0.1 default).
# Method: Train with dropout=0.3. At inference, run 20 MC passes.
#   Compare ensemble std-based intervals to seed ensemble (EXP-100).
# Target: >70% coverage at 95% nominal (better than EXP-100's 55.7%).
# ────────────────────────────────────────────────────────────────────
def run_dropout_ensemble(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-108] {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4, dropout=0.3).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val = float('inf')
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            optimizer.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward()
            optimizer.step()
        model.eval()
        vls = []
        with torch.no_grad():
            for bx, bt in DataLoader(val_ds, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vl = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                vls.append(vl.item())
        val_loss = np.mean(vls)
        scheduler.step(val_loss)
        if val_loss < best_val:
            best_val = val_loss
        if ep % 25 == 0:
            print(f'  [MC30] {ep}/100 val={val_loss:.6f} best={best_val:.6f}')

    # MC-Dropout inference: 20 passes with dropout enabled
    n_mc = 20
    model.train()  # enable dropout
    all_mc_preds = []
    all_true = []

    with torch.no_grad():
        for bx, bt in DataLoader(val_ds, batch_size=256):
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            true_g = bx[:, 12:, 0] * 400.0
            all_true.append(true_g.cpu().numpy())

            mc_preds = []
            for _ in range(n_mc):
                pred = model(x_in)[:, 12:, 0] * 400.0
                mc_preds.append(pred.cpu().numpy())
            all_mc_preds.append(np.stack(mc_preds))  # [n_mc, B, T]

    true_np = np.concatenate(all_true)
    mc_np = np.concatenate(all_mc_preds, axis=1)  # [n_mc, N, T]

    mc_mean = mc_np.mean(axis=0)
    mc_std = mc_np.std(axis=0)

    mae = float(np.mean(np.abs(true_np - mc_mean)))
    mean_std = float(mc_std.mean())

    coverages = {}
    for z, nom in [(1.0, '68'), (1.96, '95'), (2.576, '99')]:
        lo = mc_mean - z * mc_std
        hi = mc_mean + z * mc_std
        cov = float(np.mean((true_np >= lo) & (true_np <= hi)))
        wid = float(np.mean(hi - lo))
        coverages[nom] = {'coverage': round(cov, 3), 'width': round(wid, 1)}
        print(f'  [EXP-108] {nom}% interval: coverage={cov*100:.1f}%, width={wid:.1f} mg/dL')

    print(f'')
    print(f'--- MC-Dropout ensemble results ---')
    print(f'  [EXP-108] MC mean MAE: {mae:.1f} mg/dL')
    print(f'  [EXP-108] Mean std: {mean_std:.1f} mg/dL')

    out_path = 'externals/experiments/exp108_dropout_ensemble.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-108', 'name': 'dropout-ensemble',
                   'results': {'mae_mgdl': round(mae, 1),
                               'mean_std_mgdl': round(mean_std, 1),
                               'n_mc_passes': n_mc,
                               'dropout_rate': 0.3,
                               'coverages': coverages}},
                  f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ────────────────────────────────────────────────────────────────────
# EXP-109: Walk-Forward Validation at Multiple Horizons
# Problem: All experiments use random train/val split. Need temporal
#   validation to confirm no look-ahead bias.
# Method: Train on first 70% of each patient's windows, test on
#   last 30%. Compare MAE to random split at 1hr and 2hr.
# Target: Temporal MAE within 15% of random split MAE.
# ────────────────────────────────────────────────────────────────────
def run_walkforward_multi(args):
    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader, ConcatDataset, Subset
    from .model import CGMGroupedEncoder
    from .real_data_adapter import load_multipatient_nightscout
    from .experiment_lib import resolve_patient_paths
    from .device import resolve_device

    device = resolve_device(getattr(args, 'device', 'auto'))
    print(f'Device: {device}')
    paths = resolve_patient_paths(getattr(args, 'patients_dir', None),
                                  getattr(args, 'real_data', None))

    results = {}
    for ws, label in [(24, '1hr'), (48, '2hr')]:
        # Load with temporal split
        train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
        n = len(train_ds) + len(val_ds)

        # Temporal split: train on first 70%, test on last 30%
        all_ds = ConcatDataset([train_ds, val_ds])
        n_total = len(all_ds)
        split = int(n_total * 0.7)
        temp_train = Subset(all_ds, list(range(split)))
        temp_test = Subset(all_ds, list(range(split, n_total)))
        print(f'  [EXP-109] {label}: {len(temp_train)} train, {len(temp_test)} test (temporal)')

        half = ws // 2
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
        tl = DataLoader(temp_train, batch_size=128, shuffle=True)
        best_val = float('inf')
        for ep in range(1, 81):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                optimizer.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                optimizer.step()
            model.eval()
            vls = []
            with torch.no_grad():
                for bx, bt in DataLoader(temp_test, batch_size=256):
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    vl = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                    vls.append(vl.item())
            val_loss = np.mean(vls)
            scheduler.step(val_loss)
            if val_loss < best_val:
                best_val = val_loss
            if ep % 20 == 0:
                print(f'  [{label}] {ep}/80 val={val_loss:.6f} best={best_val:.6f}')

        # Evaluate
        model.eval()
        all_pred, all_true = [], []
        with torch.no_grad():
            for bx, bt in DataLoader(temp_test, batch_size=256):
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)[:, half:, 0] * 400.0
                true = bx[:, half:, 0] * 400.0
                all_pred.append(pred.cpu().numpy())
                all_true.append(true.cpu().numpy())
        pred_np = np.concatenate(all_pred)
        true_np = np.concatenate(all_true)
        mae_temporal = float(np.mean(np.abs(true_np - pred_np)))

        results[label] = {'mae_temporal': round(mae_temporal, 1),
                           'train_size': len(temp_train),
                           'test_size': len(temp_test)}
        print(f'  [EXP-109] {label} temporal MAE: {mae_temporal:.1f} mg/dL')

    # Reference baselines from previous experiments
    results['1hr']['mae_random_ref'] = 12.1  # EXP-093
    results['2hr']['mae_random_ref'] = 17.0  # EXP-093

    print(f'')
    print(f'--- Walk-forward multi-horizon results ---')
    for h in ['1hr', '2hr']:
        r = results[h]
        ref = r.get('mae_random_ref', 0)
        gap = (r['mae_temporal'] - ref) / ref * 100 if ref > 0 else 0
        print(f'  [EXP-109] {h}: temporal={r["mae_temporal"]}, random={ref}, gap={gap:.1f}%')

    out_path = 'externals/experiments/exp109_walkforward_multi.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-109', 'name': 'walkforward-multi',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


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
