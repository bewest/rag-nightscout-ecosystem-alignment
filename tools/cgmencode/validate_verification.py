"""
validate_verification.py — Multi-objective validation on held-out data.

Evaluates all 4 architecture objectives on verification splits that the
models have never seen during training:

  EXP-122  event-detection-verification
  EXP-123  override-recommendation-verification
  EXP-124  drift-tir-correlation
  EXP-125  composite-verification

Each suite can run independently or together via run_all_suites().
Results are structured dicts suitable for JSON serialization and
experiment logging.

Usage (via experiment runner):
    python3 -m tools.cgmencode.run_experiment event-detection-verification \\
        --patients-dir externals/ns-data/patients --real-data

Or programmatically:
    from tools.cgmencode.validate_verification import run_all_suites
    results = run_all_suites('externals/ns-data/patients')
"""

import json
import os
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .schema import (
    NORMALIZATION_SCALES, IDX_GLUCOSE, IDX_IOB, IDX_COB,
    NUM_FEATURES, OVERRIDE_TYPES,
)
from .real_data_adapter import build_nightscout_grid
from .label_events import (
    build_classifier_dataset, extract_override_events,
    build_pre_event_windows, extract_extended_tabular,
    EXTENDED_LABEL_MAP,
)
from .event_classifier import (
    train_event_classifier, predict_events, score_override_candidates,
)
from .evaluate import clinical_summary, override_accuracy
from .state_tracker import ISFCRTracker, DriftDetector

GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']

# Reverse map: index → event name
IDX_TO_EVENT = {v: k for k, v in EXTENDED_LABEL_MAP.items()}


# ─── Helpers ───────────────────────────────────────────────────────

def _patient_dirs(patients_dir: str, split: str = 'verification') -> List[Path]:
    """List patient directories that have the given split."""
    pdir = Path(patients_dir)
    return sorted(
        d for d in pdir.iterdir()
        if d.is_dir() and (d / split).is_dir()
    )


def _safe_div(a, b, default=0.0):
    return a / b if b > 0 else default


def _per_class_metrics(y_true, y_pred, label_map):
    """Compute per-class precision/recall/F1."""
    results = {}
    for name, idx in label_map.items():
        if idx == 0:  # skip 'none' class
            continue
        tp = int(np.sum((y_true == idx) & (y_pred == idx)))
        fp = int(np.sum((y_true != idx) & (y_pred == idx)))
        fn = int(np.sum((y_true == idx) & (y_pred != idx)))
        prec = _safe_div(tp, tp + fp)
        rec = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * prec * rec, prec + rec)
        results[name] = {
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'f1': round(f1, 4),
            'tp': tp, 'fp': fp, 'fn': fn,
            'support': tp + fn,
        }
    return results


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# ─── Suite A: Event Detection on Verification Data ────────────────

def run_event_detection_verification(patients_dir, **kwargs):
    """EXP-122: Train event classifier on training data, evaluate on
    verification data. Measures per-class F1 and generalization gap.

    Returns dict with training_metrics, verification_metrics,
    per_patient results, and generalization_gap.
    """
    patients_dir = str(patients_dir)
    print('EXP-122: Event Detection Verification')
    print('=' * 50)

    # Phase 1: Train classifier on training data
    print('  Phase 1: Training classifier on training splits...')
    train_dataset = build_classifier_dataset(patients_dir, split='training')
    if train_dataset is None:
        return {'status': 'error', 'reason': 'No training data found'}

    train_result = train_event_classifier(
        train_dataset['tabular'], train_dataset['labels'],
        feature_names=train_dataset['feature_names'],
        val_fraction=0.2,
    )
    model = train_result['model']
    train_metrics = train_result['metrics']
    print(f'    Training F1: {train_metrics.get("macro_f1", 0):.3f}  '
          f'Accuracy: {train_metrics.get("accuracy", 0):.3f}')

    # Phase 2: Build verification dataset
    print('  Phase 2: Building verification dataset...')
    verif_dataset = build_classifier_dataset(patients_dir, split='verification')
    if verif_dataset is None:
        return {
            'status': 'partial',
            'reason': 'No verification events found',
            'training_metrics': train_metrics,
            'classifier_model': model,
        }

    # Phase 3: Run inference on verification data
    print('  Phase 3: Running inference on verification data...')
    verif_tabular = verif_dataset['tabular']
    verif_labels = verif_dataset['labels']
    verif_meta = verif_dataset['metadata']

    # Predict using the XGBoost model directly for label predictions
    label_to_idx = train_result.get('label_to_idx', {})
    idx_to_label = train_result.get('idx_to_label', {})

    # Get raw predictions from model
    if hasattr(model, 'predict'):
        y_pred_raw = model.predict(verif_tabular)
        y_proba = model.predict_proba(verif_tabular) if hasattr(model, 'predict_proba') else None
    else:
        return {'status': 'error', 'reason': 'Model has no predict method'}

    # Map predictions back to original label space
    if idx_to_label:
        y_pred = np.array([idx_to_label.get(int(p), int(p)) for p in y_pred_raw])
    else:
        y_pred = y_pred_raw

    # Overall verification metrics
    accuracy = float(np.mean(y_pred == verif_labels))
    per_class = _per_class_metrics(verif_labels, y_pred, EXTENDED_LABEL_MAP)

    # Macro F1
    f1_values = [m['f1'] for m in per_class.values() if m['support'] > 0]
    macro_f1 = float(np.mean(f1_values)) if f1_values else 0.0

    verif_metrics = {
        'accuracy': round(accuracy, 4),
        'macro_f1': round(macro_f1, 4),
        'per_class': per_class,
        'n_windows': len(verif_labels),
        'n_positive': int(np.sum(verif_labels > 0)),
        'class_distribution': {
            IDX_TO_EVENT.get(int(k), str(k)): int(v)
            for k, v in sorted(Counter(verif_labels).items())
        },
    }
    print(f'    Verification F1: {macro_f1:.3f}  '
          f'Accuracy: {accuracy:.3f}  '
          f'({len(verif_labels)} windows, {int(np.sum(verif_labels > 0))} positive)')

    # Phase 4: Per-patient breakdown
    print('  Phase 4: Per-patient breakdown...')
    per_patient = {}
    patient_names = list(set(m.get('patient', 'unknown') for m in verif_meta))
    for pname in sorted(patient_names):
        mask = np.array([m.get('patient') == pname for m in verif_meta])
        if not np.any(mask):
            continue
        p_labels = verif_labels[mask]
        p_preds = y_pred[mask]
        p_acc = float(np.mean(p_preds == p_labels))
        p_per_class = _per_class_metrics(p_labels, p_preds, EXTENDED_LABEL_MAP)
        p_f1s = [m['f1'] for m in p_per_class.values() if m['support'] > 0]
        per_patient[pname] = {
            'accuracy': round(p_acc, 4),
            'macro_f1': round(float(np.mean(p_f1s)), 4) if p_f1s else 0.0,
            'n_windows': int(np.sum(mask)),
            'per_class': p_per_class,
        }
        print(f'    {pname}: F1={per_patient[pname]["macro_f1"]:.3f} '
              f'acc={p_acc:.3f} ({int(np.sum(mask))} windows)')

    # Phase 5: Temporal precision (lead time analysis)
    print('  Phase 5: Lead time analysis...')
    lead_times = []
    for i, m in enumerate(verif_meta):
        if verif_labels[i] > 0 and y_pred[i] == verif_labels[i]:
            lt = m.get('lead_time_min', None)
            if lt is not None:
                lead_times.append(lt)

    lead_time_stats = {}
    if lead_times:
        lead_arr = np.array(lead_times)
        lead_time_stats = {
            'mean_min': round(float(np.mean(lead_arr)), 1),
            'median_min': round(float(np.median(lead_arr)), 1),
            'std_min': round(float(np.std(lead_arr)), 1),
            'pct_over_15min': round(float(np.mean(lead_arr >= 15)) * 100, 1),
            'pct_over_30min': round(float(np.mean(lead_arr >= 30)) * 100, 1),
            'n_correct_with_lead': len(lead_times),
        }
        print(f'    Mean lead time: {lead_time_stats["mean_min"]:.1f} min  '
              f'>15min: {lead_time_stats["pct_over_15min"]:.1f}%  '
              f'>30min: {lead_time_stats["pct_over_30min"]:.1f}%')

    # Phase 6: Generalization gap
    train_f1 = train_metrics.get('macro_f1', 0)
    gap = train_f1 - macro_f1
    gap_pct = _safe_div(gap, train_f1) * 100
    print(f'  Generalization gap: {gap:.3f} ({gap_pct:.1f}% degradation)')

    results = {
        'status': 'ok',
        'experiment': 'EXP-122',
        'name': 'event-detection-verification',
        'training_metrics': train_metrics,
        'verification_metrics': verif_metrics,
        'per_patient': per_patient,
        'lead_time_stats': lead_time_stats,
        'generalization_gap': {
            'train_f1': round(train_f1, 4),
            'verif_f1': round(macro_f1, 4),
            'absolute_gap': round(gap, 4),
            'relative_gap_pct': round(gap_pct, 1),
        },
        'classifier_model': model,
        'train_result': train_result,
    }

    # Save results (without non-serializable model)
    out_path = 'externals/experiments/exp122_event_detection_verification.json'
    save_results = {k: v for k, v in results.items()
                    if k not in ('classifier_model', 'train_result')}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(save_results, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results → {out_path}')

    return results


# ─── Suite B: Override Recommendation on Verification Data ────────

def run_override_recommendation_verification(patients_dir, *,
                                              classifier_model=None,
                                              train_result=None,
                                              **kwargs):
    """EXP-123: Evaluate override recommendations on verification data.

    If classifier_model is provided (from Suite A), reuses it.
    Otherwise trains a new classifier on training data.

    Returns dict with override precision/recall/F1, false alarm rate,
    type confusion matrix, and lead time quality.
    """
    patients_dir = str(patients_dir)
    print('\nEXP-123: Override Recommendation Verification')
    print('=' * 50)

    # Get or train classifier
    if classifier_model is None:
        print('  Training classifier (no model passed)...')
        train_dataset = build_classifier_dataset(patients_dir, split='training')
        if train_dataset is None:
            return {'status': 'error', 'reason': 'No training data'}
        train_result = train_event_classifier(
            train_dataset['tabular'], train_dataset['labels'],
            feature_names=train_dataset['feature_names'],
        )
        classifier_model = train_result['model']

    # Process each verification patient
    patient_results = {}
    all_suggested = []
    all_actual = []
    total_hours = 0.0

    for pdir in _patient_dirs(patients_dir, 'verification'):
        vpath = pdir / 'verification'
        patient_name = pdir.name
        tx_path = vpath / 'treatments.json'
        ds_path = vpath / 'devicestatus.json'

        if not tx_path.exists():
            continue

        # Extract actual override events
        actual_events, stats = extract_override_events(
            str(tx_path),
            str(ds_path) if ds_path.exists() else None,
        )

        # Build verification grid
        grid_df, features = build_nightscout_grid(str(vpath))
        if grid_df is None or features is None:
            continue

        # Add time encoding for pre-event windows
        hours = grid_df.index.hour + grid_df.index.minute / 60.0
        grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
        grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)

        # Build windows around actual events
        win_features, win_labels, win_meta = build_pre_event_windows(
            grid_df, actual_events, window_steps=12,
        )
        if len(win_features) == 0:
            continue

        # Extract tabular features
        tabular, feat_names = extract_extended_tabular(
            win_features, win_labels, win_meta,
        )

        # Score override candidates
        overrides = score_override_candidates(
            classifier_model, tabular, win_meta, min_prob=0.3,
        )

        # Build suggested/actual lists for override_accuracy
        suggested_list = []
        for i, ov in enumerate(overrides):
            suggested_list.append({
                'timestamp_idx': i,
                'event_type': ov.get('predicted_event', ov.get('override_type', '')),
            })

        actual_list = []
        for i, m in enumerate(win_meta):
            if win_labels[i] > 0:
                actual_list.append({
                    'timestamp_idx': i,
                    'event_type': IDX_TO_EVENT.get(int(win_labels[i]), 'unknown'),
                })

        # Score override accuracy
        if suggested_list and actual_list:
            acc = override_accuracy(suggested_list, actual_list, lead_window_steps=6)
        else:
            acc = {'precision': 0, 'recall': 0, 'f1': 0,
                   'mean_lead_time': 0, 'n_suggested': len(suggested_list),
                   'n_actual': len(actual_list), 'true_positives': 0}

        # Duration in hours for false alarm rate
        data_hours = len(features) * 5 / 60.0  # 5-min intervals
        total_hours += data_hours
        false_alarms = acc['n_suggested'] - acc['true_positives']

        # Type confusion: what override types are suggested vs actual
        type_confusion = defaultdict(lambda: defaultdict(int))
        for ov in overrides:
            pred_type = ov.get('override_type', 'unknown')
            pred_event = ov.get('predicted_event', 'unknown')
            type_confusion[pred_event][pred_type] += 1

        patient_results[patient_name] = {
            'override_accuracy': acc,
            'n_overrides_suggested': len(overrides),
            'n_actual_events': len(actual_events),
            'false_alarms': false_alarms,
            'false_alarm_rate_per_hour': round(
                _safe_div(false_alarms, data_hours), 3),
            'data_hours': round(data_hours, 1),
            'type_confusion': dict(type_confusion),
        }

        all_suggested.extend(suggested_list)
        all_actual.extend(actual_list)

        print(f'    {patient_name}: prec={acc["precision"]:.2f} '
              f'rec={acc["recall"]:.2f} f1={acc["f1"]:.2f} '
              f'({acc["n_suggested"]} suggested, {acc["n_actual"]} actual)')

    # Aggregate metrics
    if all_suggested and all_actual:
        # Recompute from per-patient TP/FP counts
        total_tp = sum(pr['override_accuracy']['true_positives']
                       for pr in patient_results.values())
        total_suggested = sum(pr['n_overrides_suggested']
                              for pr in patient_results.values())
        total_actual = sum(pr['override_accuracy']['n_actual']
                           for pr in patient_results.values())
        total_false = total_suggested - total_tp

        agg_prec = _safe_div(total_tp, total_suggested)
        agg_rec = _safe_div(total_tp, total_actual)
        agg_f1 = _safe_div(2 * agg_prec * agg_rec, agg_prec + agg_rec)
    else:
        agg_prec = agg_rec = agg_f1 = 0.0
        total_tp = total_suggested = total_actual = total_false = 0

    aggregate = {
        'precision': round(agg_prec, 4),
        'recall': round(agg_rec, 4),
        'f1': round(agg_f1, 4),
        'total_suggested': total_suggested,
        'total_actual': total_actual,
        'true_positives': total_tp,
        'false_alarms': total_false,
        'false_alarm_rate_per_hour': round(
            _safe_div(total_false, total_hours), 3),
        'total_verification_hours': round(total_hours, 1),
        'lead_time_quality_pct_over_15min': round(
            _safe_div(total_tp, max(total_actual, 1)) * 100, 1),
    }

    print(f'\n  Aggregate: prec={agg_prec:.3f} rec={agg_rec:.3f} '
          f'f1={agg_f1:.3f}  FA/hr={aggregate["false_alarm_rate_per_hour"]:.3f}')

    results = {
        'status': 'ok',
        'experiment': 'EXP-123',
        'name': 'override-recommendation-verification',
        'aggregate': aggregate,
        'per_patient': patient_results,
    }

    out_path = 'externals/experiments/exp123_override_recommendation_verification.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results → {out_path}')

    return results


# ─── Suite C: Drift-TIR Correlation ───────────────────────────────

def run_drift_tir_correlation(patients_dir, **kwargs):
    """EXP-124: Measure whether ISF/CR drift detection correlates with
    TIR (Time In Range) changes on verification data.

    For each patient's verification data:
    - Run ISFCRTracker through the glucose timeline
    - Compute rolling 24h TIR windows
    - Correlate drift magnitude with TIR delta from baseline

    Returns dict with per-patient and aggregate correlation metrics.
    """
    patients_dir = str(patients_dir)
    print('\nEXP-124: Drift-TIR Correlation')
    print('=' * 50)

    WINDOW_24H = 288  # 24h in 5-min steps
    per_patient = {}
    all_drifts = []
    all_tir_deltas = []

    for pdir in _patient_dirs(patients_dir, 'verification'):
        vpath = pdir / 'verification'
        patient_name = pdir.name

        # Load verification data
        grid_df, features = build_nightscout_grid(str(vpath))
        if features is None or len(features) < WINDOW_24H:
            print(f'    {patient_name}: insufficient data, skipping')
            continue

        glucose_norm = features[:, IDX_GLUCOSE]
        iob_norm = features[:, IDX_IOB]
        cob_norm = features[:, IDX_COB]

        # Load patient profile for nominal ISF/CR
        profile_path = vpath / 'profile.json'
        nominal_isf, nominal_cr = 40.0, 10.0
        if profile_path.exists():
            try:
                with open(profile_path) as f:
                    prof = json.load(f)
                if isinstance(prof, list):
                    prof = prof[0] if prof else {}
                store = prof.get('store', {})
                default = store.get('Default', store.get(
                    next(iter(store), ''), {}))
                sens = default.get('sens', [{}])
                cr = default.get('carbratio', [{}])
                if sens and 'value' in sens[0]:
                    nominal_isf = float(sens[0]['value'])
                if cr and 'value' in cr[0]:
                    nominal_cr = float(cr[0]['value'])
            except (json.JSONDecodeError, KeyError, StopIteration):
                pass

        # Run Kalman tracker through all data in 2h chunks
        tracker = ISFCRTracker(nominal_isf=nominal_isf, nominal_cr=nominal_cr)
        detector = DriftDetector(tracker)

        chunk_size = 24  # 2 hours
        n_chunks = len(features) // chunk_size
        drift_trajectory = []

        glucose_scale = NORMALIZATION_SCALES['glucose']
        iob_scale = NORMALIZATION_SCALES['iob']
        cob_scale = NORMALIZATION_SCALES['cob']

        for i in range(n_chunks):
            s = i * chunk_size
            e = s + chunk_size
            glucose_raw = glucose_norm[s:e] * glucose_scale
            iob_raw = iob_norm[s:e] * iob_scale
            cob_raw = cob_norm[s:e] * cob_scale

            # Skip chunks with NaN glucose
            if np.any(np.isnan(glucose_raw)):
                drift_trajectory.append(None)
                continue

            # Simple physics residual
            residual = float(np.mean(np.diff(glucose_raw)))
            iob_delta = float(iob_raw[-1] - iob_raw[0])
            cob_delta = float(cob_raw[-1] - cob_raw[0])

            tracker.update(residual, iob_delta, cob_delta)
            classification = detector.classify()
            drift_trajectory.append({
                'chunk': i,
                'state': classification['state'],
                'isf_drift_pct': classification['isf_drift_pct'],
                'cr_drift_pct': classification['cr_drift_pct'],
                'confidence': classification['confidence'],
            })

        # Compute rolling 24h TIR
        glucose_mgdl = glucose_norm * glucose_scale
        n_24h_windows = max(0, len(glucose_mgdl) - WINDOW_24H)
        tir_series = []
        step = max(1, WINDOW_24H // 4)  # stride by 6h

        for start in range(0, n_24h_windows, step):
            window = glucose_mgdl[start:start + WINDOW_24H]
            valid = window[~np.isnan(window)]
            if len(valid) < WINDOW_24H // 2:
                tir_series.append(None)
                continue
            in_range = np.sum((valid >= 70) & (valid <= 180))
            tir = float(in_range / len(valid)) * 100
            tir_series.append(tir)

        # Baseline TIR (first valid window)
        baseline_tir = next((t for t in tir_series if t is not None), None)
        if baseline_tir is None:
            print(f'    {patient_name}: no valid TIR windows, skipping')
            continue

        # Pair drift magnitude with TIR delta for each time period
        patient_drifts = []
        patient_tir_deltas = []

        valid_traj = [d for d in drift_trajectory if d is not None]
        valid_tir = [(i, t) for i, t in enumerate(tir_series) if t is not None]

        # Align by time: map drift chunks to TIR windows
        for ti, tir_val in valid_tir:
            tir_delta = tir_val - baseline_tir
            # Find corresponding drift state (map TIR window start to chunk)
            chunk_idx = (ti * step) // chunk_size
            if chunk_idx < len(drift_trajectory) and drift_trajectory[chunk_idx] is not None:
                drift_mag = abs(drift_trajectory[chunk_idx]['isf_drift_pct']) + \
                            abs(drift_trajectory[chunk_idx]['cr_drift_pct'])
                patient_drifts.append(drift_mag)
                patient_tir_deltas.append(tir_delta)

        # Compute correlation
        correlation = None
        if len(patient_drifts) >= 3:
            d_arr = np.array(patient_drifts)
            t_arr = np.array(patient_tir_deltas)
            if np.std(d_arr) > 0 and np.std(t_arr) > 0:
                correlation = float(np.corrcoef(d_arr, t_arr)[0, 1])

        # Drift detection rate
        n_non_stable = sum(1 for d in valid_traj if d['state'] != 'stable')
        drift_rate = _safe_div(n_non_stable, len(valid_traj)) * 100

        # False signal: non-stable but TIR is actually stable (±3%)
        false_signals = 0
        for i, d in enumerate(valid_traj):
            if d['state'] != 'stable':
                chunk_time = d['chunk']
                ti_idx = chunk_time * chunk_size // step
                if ti_idx < len(tir_series) and tir_series[ti_idx] is not None:
                    if abs(tir_series[ti_idx] - baseline_tir) <= 3.0:
                        false_signals += 1

        per_patient[patient_name] = {
            'correlation': round(correlation, 4) if correlation is not None else None,
            'n_drift_chunks': len(valid_traj),
            'n_tir_windows': len(valid_tir),
            'n_paired': len(patient_drifts),
            'drift_detection_rate_pct': round(drift_rate, 1),
            'n_non_stable': n_non_stable,
            'false_signals': false_signals,
            'false_signal_rate_pct': round(
                _safe_div(false_signals, max(n_non_stable, 1)) * 100, 1),
            'baseline_tir': round(baseline_tir, 1),
            'nominal_isf': nominal_isf,
            'nominal_cr': nominal_cr,
        }

        all_drifts.extend(patient_drifts)
        all_tir_deltas.extend(patient_tir_deltas)

        corr_str = f'{correlation:.3f}' if correlation is not None else 'N/A'
        print(f'    {patient_name}: corr={corr_str} '
              f'drift_rate={drift_rate:.1f}% '
              f'baseline_TIR={baseline_tir:.1f}% '
              f'({len(patient_drifts)} paired)')

    # Aggregate correlation
    agg_correlation = None
    if len(all_drifts) >= 5:
        d_arr = np.array(all_drifts)
        t_arr = np.array(all_tir_deltas)
        if np.std(d_arr) > 0 and np.std(t_arr) > 0:
            agg_correlation = float(np.corrcoef(d_arr, t_arr)[0, 1])

    # Expected: negative correlation (more drift → lower TIR)
    aggregate = {
        'pearson_correlation': round(agg_correlation, 4) if agg_correlation is not None else None,
        'expected_sign': 'negative (drift should predict TIR decrease)',
        'correlation_matches_expectation': (
            agg_correlation is not None and agg_correlation < 0),
        'n_total_paired': len(all_drifts),
        'n_patients_with_correlation': sum(
            1 for p in per_patient.values() if p['correlation'] is not None),
        'mean_drift_detection_rate_pct': round(float(np.mean([
            p['drift_detection_rate_pct'] for p in per_patient.values()
        ])), 1) if per_patient else 0,
        'mean_false_signal_rate_pct': round(float(np.mean([
            p['false_signal_rate_pct'] for p in per_patient.values()
        ])), 1) if per_patient else 0,
    }

    corr_str = f'{agg_correlation:.4f}' if agg_correlation is not None else 'N/A'
    print(f'\n  Aggregate correlation: {corr_str} '
          f'(expected: negative)  {len(all_drifts)} paired observations')

    results = {
        'status': 'ok',
        'experiment': 'EXP-124',
        'name': 'drift-tir-correlation',
        'aggregate': aggregate,
        'per_patient': per_patient,
    }

    out_path = 'externals/experiments/exp124_drift_tir_correlation.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results → {out_path}')

    return results


# ─── Suite D: Composite Pipeline on Verification Data ─────────────

def run_composite_verification(patients_dir, *, classifier_model=None,
                                checkpoint_path=None, **kwargs):
    """EXP-125: Run full decision pipeline on verification data.

    Tests whether forecast + event detection + drift tracking compose
    to produce better-informed outputs than forecasting alone.

    Runs run_decision() at representative windows (every 6h) per patient.
    Aggregates event detection rate, override suggestion rate, forecast
    accuracy, and clinical outcome correlation.
    """
    patients_dir = str(patients_dir)
    print('\nEXP-125: Composite Pipeline Verification')
    print('=' * 50)

    # Try to load grouped model for forecasting
    model = None
    if checkpoint_path:
        try:
            from .hindcast import load_model
            model = load_model(checkpoint_path)
            print(f'  Loaded model from {checkpoint_path}')
        except Exception as e:
            print(f'  Warning: Could not load model: {e}')

    # Find default checkpoint if not provided
    if model is None:
        for cp in ['externals/experiments/exp051_seed456.pth',
                    'externals/experiments/exp043_masked_grouped.pth',
                    'checkpoints/grouped_multipatient.pth']:
            if os.path.exists(cp):
                try:
                    from .hindcast import load_model
                    model = load_model(cp)
                    print(f'  Loaded model from {cp}')
                    break
                except Exception:
                    continue

    # Train classifier if not provided
    if classifier_model is None:
        print('  Training event classifier...')
        train_dataset = build_classifier_dataset(patients_dir, split='training')
        if train_dataset is not None:
            train_result = train_event_classifier(
                train_dataset['tabular'], train_dataset['labels'],
                feature_names=train_dataset['feature_names'],
            )
            classifier_model = train_result['model']

    per_patient = {}
    all_results = []
    STRIDE_STEPS = 72  # every 6 hours

    for pdir in _patient_dirs(patients_dir, 'verification'):
        vpath = pdir / 'verification'
        patient_name = pdir.name

        grid_df, features = build_nightscout_grid(str(vpath))
        if features is None or len(features) < 24:
            continue

        # Load profile
        profile_path = vpath / 'profile.json'
        isf, cr = 40.0, 10.0
        if profile_path.exists():
            try:
                with open(profile_path) as f:
                    prof = json.load(f)
                if isinstance(prof, list):
                    prof = prof[0] if prof else {}
                store = prof.get('store', {})
                default = store.get('Default', store.get(
                    next(iter(store), ''), {}))
                sens = default.get('sens', [{}])
                carbratio = default.get('carbratio', [{}])
                if sens and 'value' in sens[0]:
                    isf = float(sens[0]['value'])
                if carbratio and 'value' in carbratio[0]:
                    cr = float(carbratio[0]['value'])
            except (json.JSONDecodeError, KeyError, StopIteration):
                pass

        # Build classifier features for this patient's verification data
        clf_tabular = None
        if classifier_model is not None:
            try:
                actual_events, _ = extract_override_events(
                    str(vpath / 'treatments.json'),
                    str(vpath / 'devicestatus.json') if (vpath / 'devicestatus.json').exists() else None,
                )
                hours = grid_df.index.hour + grid_df.index.minute / 60.0
                grid_df_copy = grid_df.copy()
                grid_df_copy['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
                grid_df_copy['time_cos'] = np.cos(2 * np.pi * hours / 24.0)
                win_feat, win_lab, win_meta = build_pre_event_windows(
                    grid_df_copy, actual_events, window_steps=12,
                )
                if len(win_feat) > 0:
                    clf_tabular, _ = extract_extended_tabular(
                        win_feat, win_lab, win_meta)
            except Exception:
                pass

        # Sample representative windows
        window_indices = list(range(12, len(features) - 12, STRIDE_STEPS))
        if not window_indices:
            window_indices = [len(features) // 2]

        n_events_detected = 0
        n_overrides_suggested = 0
        n_drift_non_stable = 0
        forecast_maes = []
        n_windows = 0

        for center_idx in window_indices:
            # Skip windows with NaN glucose
            start = max(0, center_idx - 12)
            end = min(len(features), center_idx + 12)
            glucose_window = features[start:end, IDX_GLUCOSE] * GLUCOSE_SCALE
            if np.any(np.isnan(glucose_window)):
                continue

            try:
                from .hindcast_composite import run_decision
                result = run_decision(
                    model=model,
                    features=features,
                    df=grid_df,
                    center_idx=center_idx,
                    history=12,
                    horizon=12,
                    isf=isf,
                    cr=cr,
                    classifier_model=classifier_model,
                    classifier_features=clf_tabular,
                )
            except Exception:
                continue

            n_windows += 1

            # Tally event detections
            ec = result.get('event_classification', {})
            if ec.get('status') == 'ok' and ec.get('n_events', 0) > 0:
                n_events_detected += 1

            # Tally override suggestions from drift
            dt = result.get('drift_tracking', {})
            if dt.get('suggested_override') is not None:
                n_overrides_suggested += 1
            if dt.get('classification', 'stable') != 'stable':
                n_drift_non_stable += 1

            # Forecast MAE
            fc = result.get('forecast', {})
            if 'mae_mgdl' in fc and not np.isnan(fc['mae_mgdl']):
                forecast_maes.append(fc['mae_mgdl'])

            all_results.append(result)

        if n_windows == 0:
            continue

        per_patient[patient_name] = {
            'n_windows': n_windows,
            'event_detection_rate_pct': round(
                _safe_div(n_events_detected, n_windows) * 100, 1),
            'override_suggestion_rate_pct': round(
                _safe_div(n_overrides_suggested, n_windows) * 100, 1),
            'drift_non_stable_rate_pct': round(
                _safe_div(n_drift_non_stable, n_windows) * 100, 1),
            'mean_forecast_mae': round(
                float(np.mean(forecast_maes)), 1) if forecast_maes else None,
            'n_forecast_windows': len(forecast_maes),
        }

        mae_str = f'{np.mean(forecast_maes):.1f}' if forecast_maes else 'N/A'
        print(f'    {patient_name}: {n_windows} windows  '
              f'events={n_events_detected}  overrides={n_overrides_suggested}  '
              f'drift={n_drift_non_stable}  MAE={mae_str}')

    # Aggregate
    if per_patient:
        total_windows = sum(p['n_windows'] for p in per_patient.values())
        total_events = sum(
            int(p['event_detection_rate_pct'] * p['n_windows'] / 100)
            for p in per_patient.values())
        total_overrides = sum(
            int(p['override_suggestion_rate_pct'] * p['n_windows'] / 100)
            for p in per_patient.values())
        all_maes = [p['mean_forecast_mae'] for p in per_patient.values()
                    if p['mean_forecast_mae'] is not None]

        aggregate = {
            'n_patients': len(per_patient),
            'total_windows': total_windows,
            'overall_event_detection_rate_pct': round(
                _safe_div(total_events, total_windows) * 100, 1),
            'overall_override_suggestion_rate_pct': round(
                _safe_div(total_overrides, total_windows) * 100, 1),
            'mean_forecast_mae': round(
                float(np.mean(all_maes)), 1) if all_maes else None,
            'has_model': model is not None,
            'has_classifier': classifier_model is not None,
        }
    else:
        aggregate = {'status': 'no_valid_patients'}

    print(f'\n  Aggregate: {aggregate.get("total_windows", 0)} windows across '
          f'{aggregate.get("n_patients", 0)} patients')

    results = {
        'status': 'ok',
        'experiment': 'EXP-125',
        'name': 'composite-verification',
        'aggregate': aggregate,
        'per_patient': per_patient,
    }

    out_path = 'externals/experiments/exp125_composite_verification.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results → {out_path}')

    return results


# ─── Orchestrator ──────────────────────────────────────────────────

def run_all_suites(patients_dir, checkpoint_path=None, **kwargs):
    """Run all 4 validation suites in sequence, passing shared state.

    Returns dict with all suite results keyed by experiment ID.
    """
    patients_dir = str(patients_dir)
    print('\n' + '╔' + '═' * 60 + '╗')
    print('║  Multi-Objective Validation on Verification Data' + ' ' * 11 + '║')
    print('╚' + '═' * 60 + '╝\n')

    all_results = {}

    # Suite A: Event Detection
    try:
        a_results = run_event_detection_verification(patients_dir, **kwargs)
        all_results['EXP-122'] = a_results
    except Exception as e:
        print(f'  Suite A failed: {e}')
        traceback.print_exc()
        all_results['EXP-122'] = {'status': 'error', 'reason': str(e)}
        a_results = {}

    # Pass classifier from Suite A to B and D
    classifier_model = a_results.get('classifier_model')
    train_result = a_results.get('train_result')

    # Suite B: Override Recommendation
    try:
        b_results = run_override_recommendation_verification(
            patients_dir,
            classifier_model=classifier_model,
            train_result=train_result,
            **kwargs,
        )
        all_results['EXP-123'] = b_results
    except Exception as e:
        print(f'  Suite B failed: {e}')
        traceback.print_exc()
        all_results['EXP-123'] = {'status': 'error', 'reason': str(e)}

    # Suite C: Drift-TIR Correlation
    try:
        c_results = run_drift_tir_correlation(patients_dir, **kwargs)
        all_results['EXP-124'] = c_results
    except Exception as e:
        print(f'  Suite C failed: {e}')
        traceback.print_exc()
        all_results['EXP-124'] = {'status': 'error', 'reason': str(e)}

    # Suite D: Composite Pipeline
    try:
        d_results = run_composite_verification(
            patients_dir,
            classifier_model=classifier_model,
            checkpoint_path=checkpoint_path,
            **kwargs,
        )
        all_results['EXP-125'] = d_results
    except Exception as e:
        print(f'  Suite D failed: {e}')
        traceback.print_exc()
        all_results['EXP-125'] = {'status': 'error', 'reason': str(e)}

    # Summary scorecard
    print('\n' + '=' * 60)
    print('  VALIDATION SCORECARD')
    print('=' * 60)

    objectives = [
        ('Forecast (MAE)', 'EXP-125', lambda r:
            f'{r.get("aggregate", {}).get("mean_forecast_mae", "N/A")} mg/dL'),
        ('Event Detection (F1)', 'EXP-122', lambda r:
            f'{r.get("verification_metrics", {}).get("macro_f1", "N/A")}'),
        ('Override Recommendation (F1)', 'EXP-123', lambda r:
            f'{r.get("aggregate", {}).get("f1", "N/A")}'),
        ('Drift-TIR Correlation', 'EXP-124', lambda r:
            f'{r.get("aggregate", {}).get("pearson_correlation", "N/A")}'),
    ]

    for name, exp_id, extractor in objectives:
        r = all_results.get(exp_id, {})
        status = r.get('status', 'not_run')
        if status == 'ok':
            value = extractor(r)
            rating = '✅' if value != 'N/A' and value != 'None' else '⚠️'
        elif status == 'partial':
            value = 'partial data'
            rating = '⚠️'
        else:
            value = status
            rating = '❌'
        print(f'  {rating} {name}: {value}')

    print('=' * 60)

    # Save combined results (without non-serializable objects)
    save_results = {}
    for k, v in all_results.items():
        save_results[k] = {
            sk: sv for sk, sv in v.items()
            if sk not in ('classifier_model', 'train_result')
        }

    out_path = 'externals/experiments/exp_all_validation_suites.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(save_results, f, indent=2, cls=_NumpyEncoder)
    print(f'\n  Combined results → {out_path}')

    return all_results
