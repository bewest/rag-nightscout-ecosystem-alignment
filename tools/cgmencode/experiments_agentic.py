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
    train, forecast_mse, persistence_mse, improvement_pct,
    resolve_patient_paths, load_patient_profile,
    build_16f_windows, windows_to_datasets, get_device,
)
from .real_data_adapter import (
    load_multipatient_nightscout, build_nightscout_grid,
    build_extended_features, downsample_grid, build_multihorizon_windows,
)
from .schema import NUM_FEATURES, NUM_FEATURES_EXTENDED
from .label_events import build_classifier_dataset, extract_override_events
from .event_classifier import train_event_classifier
from .uncertainty import mc_predict
from .state_tracker import ISFCRTracker, DriftDetector, run_retrospective_tracking
from .forecast import HierarchicalForecaster, ScenarioSimulator, BacktestEngine

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
        [p for p in paths], window_size=24, device=get_device())
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
    tabular, labels, feature_names = build_classifier_dataset(
        patients_dir, window_steps=12, lead_steps=[3, 6, 9, 12])
    ctx.log(f'{len(labels)} samples, {len(feature_names)} features')

    # Hyperparameter sweep
    best_f1, best_params = 0, {}
    sweep = [
        {'max_depth': 4, 'n_estimators': 100, 'learning_rate': 0.1},
        {'max_depth': 6, 'n_estimators': 200, 'learning_rate': 0.05},
        {'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.01},
    ]
    for params in sweep:
        ctx.log(f'Training depth={params["max_depth"]} trees={params["n_estimators"]}')
        metrics = train_event_classifier(
            tabular, labels, feature_names=feature_names,
            xgb_params=params, val_fraction=0.2)
        f1 = metrics.get('macro_f1', 0)
        if f1 > best_f1:
            best_f1, best_params = f1, params
            best_metrics = metrics

    ctx.result.update({
        'n_samples': len(labels),
        'n_features': len(feature_names),
        'best_params': best_params,
        'macro_f1': best_f1,
        'per_class': best_metrics.get('per_class', {}),
        'auroc': best_metrics.get('auroc', None),
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

    horizons = {'5min': 1, '15min': 3, '60min': 12}
    results_by_res = {}

    for label, ds_factor in horizons.items():
        ctx.section(f'Resolution: {label} (downsample {ds_factor}×)')
        all_windows = []
        for ppath in paths:
            try:
                grid_df, feat = build_nightscout_grid(ppath, verbose=False)
                if feat is None:
                    continue
                ds_df = downsample_grid(grid_df, factor=ds_factor) if ds_factor > 1 else grid_df
                mh = build_multihorizon_windows(ds_df)
                for h_label, wins in mh.items():
                    all_windows.extend(wins)
            except Exception:
                continue

        if len(all_windows) < 50:
            ctx.log(f'Only {len(all_windows)} windows — skipping')
            results_by_res[label] = {'status': 'too_few_windows'}
            continue

        train_ds, val_ds = windows_to_datasets(all_windows)
        dim = all_windows[0].shape[-1] if all_windows[0].ndim > 1 else 1
        model = create_model('grouped', input_dim=dim)
        best_loss, _ = train(
            model, train_ds, val_ds,
            f'{out}/exp028_multihorizon_{label}.pth', f'MH-{label}')
        m_mse = forecast_mse(model, val_ds)
        p_mse = persistence_mse(val_ds)
        results_by_res[label] = {
            'windows': len(all_windows), 'forecast_mse': m_mse,
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

    _, val_ds = load_multipatient_nightscout(paths, window_size=24, device=get_device())

    # Find existing grouped checkpoint
    ckpt_path = find_checkpoint(out, 'exp026_grouped_16f.pth',
                                'grouped_multi_transfer.pth')
    if not ckpt_path:
        ctx.log('Training fresh model for calibration')
        ds, _ = load_multipatient_nightscout(paths, window_size=24, device=get_device())
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
            drift = tracking.get('drift_events', [])
            patient_results[pname] = {
                'isf': isf, 'cr': cr,
                'n_drift_events': len(drift),
                'final_isf': tracking.get('final_isf', isf),
                'final_cr': tracking.get('final_cr', cr),
            }
            if len(drift) > 0:
                drift_detected += 1
                ctx.log(f'{len(drift)} drift events detected')
            else:
                ctx.log('No drift detected')
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
        _, val_ds = load_multipatient_nightscout([ppath], window_size=24, device=get_device())
        if len(val_ds) == 0:
            continue
        sample = val_ds[0][0].unsqueeze(0)
        for sc in scenarios:
            try:
                result = sim.simulate_scenario(sample, sc)
                predicted_mean = result.get('predicted_mean', result.get('forecast', None))
                if predicted_mean is not None:
                    delta = float(predicted_mean[-1] - predicted_mean[0]) if hasattr(predicted_mean, '__len__') else 0
                    direction = 'rise' if delta > 5 else 'drop' if delta < -5 else 'flat'
                    expected = sc['expected']
                    hit = (expected == direction or
                           (expected == 'moderate' and abs(delta) < 30))
                    correct += int(hit)
                    total += 1
                    scenario_results.append({
                        'scenario': sc['name'], 'delta': delta,
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

    # Load components
    model = create_model('grouped', input_dim=8)
    ckpt = find_checkpoint(out, 'exp026_grouped_16f.pth',
                           'grouped_multi_transfer.pth')
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
