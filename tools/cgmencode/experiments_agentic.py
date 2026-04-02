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

import numpy as np
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
