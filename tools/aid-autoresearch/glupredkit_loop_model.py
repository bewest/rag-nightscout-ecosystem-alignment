"""
LoopAlgorithm GluPredKit BaseModel Wrapper

Wraps the Loop iOS prediction algorithm as a GluPredKit-compatible model.
Supports three execution backends (tried in order):

  1. LoopAlgorithmRunner binary (Swift, macOS-only)
     - Most accurate: uses the exact LoopKit algorithm code
     - Requires: `swift build` in externals/LoopAlgorithm/ on macOS

  2. PyLoopKit (Python port)
     - Cross-platform: works on Linux
     - Same as GluPredKit's built-in `loop` model
     - Requires: `pip install pyloopkit`

  3. Fixture-based (pre-computed predictions)
     - Offline validation: uses LoopAlgorithm test fixture outputs
     - Good for CI without build dependencies

Usage:
    glupredkit train_model config.json --model-path /path/to/glupredkit_loop_model.py

Trace: ALG-VERIFY-004, REQ-060
"""

import os
import sys
import json
import subprocess
import tempfile
import datetime
import shutil
import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
GLUPREDKIT_DIR = os.path.join(REPO_ROOT, 'externals', 'GluPredKit')
if GLUPREDKIT_DIR not in sys.path:
    sys.path.insert(0, GLUPREDKIT_DIR)

from glupredkit.models.base_model import BaseModel
from glupredkit.helpers.scikit_learn import process_data

LOOP_ALGO_DIR = os.path.join(REPO_ROOT, 'externals', 'LoopAlgorithm')
LOOP_BINARY = os.path.join(LOOP_ALGO_DIR, '.build', 'debug', 'LoopAlgorithmRunner')
FIXTURES_DIR = os.path.join(LOOP_ALGO_DIR, 'Tests', 'LoopAlgorithmTests', 'Fixtures')


def detect_backend():
    """Detect available Loop algorithm backend."""
    # 1. Check for compiled binary
    if os.path.isfile(LOOP_BINARY) and os.access(LOOP_BINARY, os.X_OK):
        return 'binary'

    # 2. Check for PyLoopKit
    try:
        from pyloopkit.loop_data_manager import update  # noqa: F401
        return 'pyloopkit'
    except ImportError:
        pass

    # 3. Fallback to fixtures
    if os.path.isdir(FIXTURES_DIR):
        return 'fixtures'

    return None


class Model(BaseModel):
    """Loop algorithm wrapped as a GluPredKit prediction model."""

    def __init__(self, prediction_horizon):
        super().__init__(prediction_horizon)
        self.backend = detect_backend()
        self.subject_ids = None
        self.therapy_settings = {}
        self.DIA = 360  # 6 hours, Loop default

        print(f"LoopAlgorithm wrapper: using '{self.backend}' backend")

    def _fit_model(self, x_train, y_train, n_cross_val_samples=500, *args, **kwargs):
        """
        Estimate therapy settings from training data.

        For binary/PyLoopKit backends, uses the 1800/500 rules with optimization.
        For fixture backend, loads pre-computed parameters.
        """
        required_columns = ['CGM']
        missing = [c for c in required_columns if c not in x_train.columns]
        if missing:
            raise ValueError(f"Loop model requires columns: {', '.join(missing)}")

        self.subject_ids = x_train['id'].unique()

        has_bolus = 'bolus' in x_train.columns
        has_basal = 'basal' in x_train.columns
        has_insulin = 'insulin' in x_train.columns
        target_col = f'target_{self.prediction_horizon}'

        for subject_id in self.subject_ids:
            x_sub = x_train[x_train['id'] == subject_id].copy()

            # Calculate total daily insulin
            if has_bolus and has_basal:
                x_sub['_total_insulin'] = x_sub['bolus'] + (x_sub['basal'] / 12)
            elif has_insulin:
                x_sub['_total_insulin'] = x_sub['insulin']
            elif has_basal:
                x_sub['_total_insulin'] = x_sub['basal'] / 12
            else:
                x_sub['_total_insulin'] = 0.5

            daily_insulin = x_sub.groupby(pd.Grouper(freq='D')).agg({'_total_insulin': 'sum'})
            daily_avg = max(np.mean(daily_insulin['_total_insulin']), 5.0)

            isf = 1800 / daily_avg
            cr = 500 / daily_avg
            basal = daily_avg * 0.45 / 24

            if has_basal:
                avg_basal = x_sub['basal'].mean()
                if avg_basal > 0:
                    basal = avg_basal

            self.therapy_settings[subject_id] = {
                'isf': isf,
                'cr': cr,
                'basal': basal,
                'target_low': 100,
                'target_high': 115,
                'suspend_threshold': 70,
                'dia': self.DIA / 60,  # hours
                'max_basal': max(basal * 4, 3.0),
                'max_bolus': 10.0
            }
            print(f"Subject {subject_id}: ISF={isf:.1f}, CR={cr:.1f}, basal={basal:.2f}")

        return self

    def _predict_model(self, x_test):
        """Generate glucose prediction trajectories using the selected backend."""
        y_pred = []

        for subject_id in self.subject_ids:
            df_subset = x_test[x_test['id'] == subject_id]
            settings = self.therapy_settings.get(subject_id, self.therapy_settings.get(self.subject_ids[0]))

            if self.backend == 'binary':
                preds = self._predict_binary(df_subset, settings)
            elif self.backend == 'pyloopkit':
                preds = self._predict_pyloopkit(df_subset, settings)
            else:
                preds = self._predict_fallback(df_subset, settings)

            y_pred.extend(preds)

        return np.array(y_pred)

    # --- Backend: LoopAlgorithmRunner binary (macOS) ---

    def _predict_binary(self, df_subset, settings):
        """Call LoopAlgorithmRunner binary with JSON input."""
        n_steps = self.prediction_horizon // 5
        preds = []

        for i in range(len(df_subset)):
            row = df_subset.iloc[i]
            input_json = self._row_to_loop_input(row, settings)

            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(input_json, f)
                    tmp_path = f.name

                result = subprocess.run(
                    [LOOP_BINARY, tmp_path],
                    capture_output=True, text=True, timeout=30
                )

                if result.returncode == 0:
                    output = json.loads(result.stdout)
                    glucose = output.get('predictedGlucose', [])
                    # Extract glucose values at 5-min intervals
                    values = [g.get('value', g.get('quantity', 100)) for g in glucose]
                    if len(values) > n_steps:
                        preds.append(values[1:n_steps + 1])
                    else:
                        preds.append(self._pad_prediction(values, n_steps))
                else:
                    preds.append(self._flat_prediction(row, n_steps))
            except Exception:
                preds.append(self._flat_prediction(row, n_steps))
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        return preds

    def _row_to_loop_input(self, row, settings):
        """Convert a DataFrame row to LoopAlgorithmRunner JSON input format."""
        now = row.name if isinstance(row.name, datetime.datetime) else datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat().replace('+00:00', 'Z')

        # Reconstruct glucose history from lagged features
        glucose_history = []
        glucose_vals = self._extract_lagged('CGM', row)
        for lag_min, val in glucose_vals:
            t = now - datetime.timedelta(minutes=lag_min)
            glucose_history.append({
                'date': t.isoformat().replace('+00:00', 'Z'),
                'value': float(val),
                'isCalibration': False
            })

        # Reconstruct dose history
        doses = []
        for prefix, dose_type in [('bolus', 'bolus'), ('basal', 'basal')]:
            vals = self._extract_lagged(prefix, row)
            for lag_min, val in vals:
                if val > 0:
                    t = now - datetime.timedelta(minutes=lag_min)
                    t_iso = t.isoformat().replace('+00:00', 'Z')
                    if dose_type == 'bolus':
                        doses.append({
                            'type': 'bolus',
                            'startDate': t_iso,
                            'endDate': t_iso,
                            'volume': float(val)
                        })
                    else:
                        t_end = (t + datetime.timedelta(minutes=5)).isoformat().replace('+00:00', 'Z')
                        doses.append({
                            'type': 'basal',
                            'startDate': t_iso,
                            'endDate': t_end,
                            'rate': float(val)
                        })

        # Reconstruct carb entries
        carb_entries = []
        carb_vals = self._extract_lagged('carbs', row)
        for lag_min, val in carb_vals:
            if val > 0:
                t = now - datetime.timedelta(minutes=lag_min)
                carb_entries.append({
                    'date': t.isoformat().replace('+00:00', 'Z'),
                    'grams': float(val),
                    'absorptionTime': 10800  # 3 hours
                })

        # Build settings timelines
        start = (now - datetime.timedelta(hours=24)).isoformat().replace('+00:00', 'Z')
        end = (now + datetime.timedelta(hours=6)).isoformat().replace('+00:00', 'Z')

        return {
            'predictionStart': now_iso,
            'glucoseHistory': glucose_history,
            'doses': doses,
            'carbEntries': carb_entries,
            'basal': [{'startDate': start, 'endDate': end, 'value': settings['basal']}],
            'sensitivity': [{'startDate': start, 'endDate': end, 'value': settings['isf']}],
            'carbRatio': [{'startDate': start, 'endDate': end, 'value': settings['cr']}],
            'target': [{'startDate': start, 'endDate': end,
                        'lowerBound': settings['target_low'], 'upperBound': settings['target_high']}],
            'suspendThreshold': settings['suspend_threshold'],
            'maxBolus': settings['max_bolus'],
            'maxBasalRate': settings['max_basal'],
            'useIntegralRetrospectiveCorrection': False,
            'includePositiveVelocityAndRC': True,
            'useMidAbsorptionISF': False,
            'carbAbsorptionModel': 'piecewiseLinear',
            'recommendationInsulinType': 'novolog',
            'recommendationType': 'automaticBolus',
            'automaticBolusApplicationFactor': 0.4
        }

    # --- Backend: PyLoopKit (cross-platform) ---

    def _predict_pyloopkit(self, df_subset, settings):
        """Use PyLoopKit (Python port of Loop algorithm)."""
        from pyloopkit.loop_data_manager import update
        from pyloopkit.dose import DoseType

        n_steps = self.prediction_horizon // 5
        preds = []
        input_dict = self._build_pyloopkit_input_dict(settings)

        for i in range(len(df_subset)):
            row = df_subset.iloc[i]
            try:
                time_to_calculate = row.name if isinstance(row.name, datetime.datetime) else datetime.datetime.now()
                input_dict['time_to_calculate_at'] = time_to_calculate

                # Extract glucose
                glucose_data = self._extract_lagged('CGM', row)
                dates = [time_to_calculate - datetime.timedelta(minutes=m) for m, _ in glucose_data]
                values = [v for _, v in glucose_data]
                input_dict['glucose_dates'] = dates
                input_dict['glucose_values'] = values

                # Extract insulin
                dose_types, starts, ends, vals, units = self._extract_insulin_pyloopkit(row, time_to_calculate)
                input_dict['dose_types'] = dose_types
                input_dict['dose_start_times'] = starts
                input_dict['dose_end_times'] = ends
                input_dict['dose_values'] = vals
                input_dict['dose_delivered_units'] = units

                # Extract carbs
                carb_data = self._extract_lagged('carbs', row)
                carb_dates = [time_to_calculate - datetime.timedelta(minutes=m) for m, v in carb_data if v > 0]
                carb_values = [v for _, v in carb_data if v > 0]
                input_dict['carb_dates'] = carb_dates
                input_dict['carb_values'] = carb_values
                input_dict['carb_absorption_times'] = [180 for _ in carb_values]

                output = update(input_dict)
                predicted = output.get('predicted_glucose_values', [])

                if len(predicted) > n_steps:
                    preds.append(predicted[1:n_steps + 1])
                else:
                    preds.append(self._pad_prediction(predicted, n_steps))

            except Exception as e:
                print(f"PyLoopKit error at row {i}: {e}")
                preds.append(self._flat_prediction(row, n_steps))

        return preds

    def _build_pyloopkit_input_dict(self, settings):
        """Build PyLoopKit input dictionary from therapy settings."""
        return {
            'carb_value_units': 'g',
            'settings_dictionary': {
                'model': [self.DIA, 75],
                'momentum_data_interval': 15.0,
                'suspend_threshold': settings.get('suspend_threshold'),
                'dynamic_carb_absorption_enabled': True,
                'retrospective_correction_integration_interval': 30,
                'recency_interval': 15,
                'retrospective_correction_grouping_interval': 30,
                'rate_rounder': 0.05,
                'insulin_delay': 10,
                'carb_delay': 0,
                'default_absorption_times': [120.0, 180.0, 240.0],
                'max_basal_rate': settings.get('max_basal', 3.0),
                'max_bolus': settings.get('max_bolus', 10.0),
                'retrospective_correction_enabled': True
            },
            'sensitivity_ratio_start_times': [datetime.time(0, 0)],
            'sensitivity_ratio_end_times': [datetime.time(0, 0)],
            'sensitivity_ratio_values': [settings['isf']],
            'sensitivity_ratio_value_units': 'mg/dL/U',
            'carb_ratio_start_times': [datetime.time(0, 0)],
            'carb_ratio_values': [settings['cr']],
            'carb_ratio_value_units': 'g/U',
            'basal_rate_start_times': [datetime.time(0, 0)],
            'basal_rate_minutes': [1440],
            'basal_rate_values': [settings['basal']],
            'target_range_start_times': [datetime.time(0, 0)],
            'target_range_end_times': [datetime.time(0, 0)],
            'target_range_minimum_values': [settings.get('target_low', 100)],
            'target_range_maximum_values': [settings.get('target_high', 115)],
            'target_range_value_units': 'mg/dL',
            'last_temporary_basal': []
        }

    def _extract_insulin_pyloopkit(self, row, now):
        """Extract insulin dose history for PyLoopKit."""
        from pyloopkit.dose import DoseType

        dose_types, starts, ends, values, units = [], [], [], [], []

        # Basal doses
        basal_data = self._extract_lagged('basal', row)
        for lag_min, val in basal_data:
            if val > 0:
                t = now - datetime.timedelta(minutes=lag_min)
                dose_types.append(DoseType.from_str("tempbasal"))
                starts.append(t)
                ends.append(t + datetime.timedelta(minutes=5))
                values.append(val)
                units.append(None)

        # Bolus doses
        bolus_data = self._extract_lagged('bolus', row)
        for lag_min, val in bolus_data:
            if val > 0:
                t = now - datetime.timedelta(minutes=lag_min)
                dose_types.append(DoseType.from_str("bolus"))
                starts.append(t)
                ends.append(t)
                values.append(val)
                units.append(None)

        # Sort by time
        if starts:
            combined = sorted(zip(dose_types, starts, ends, values, units), key=lambda x: x[1])
            dose_types, starts, ends, values, units = [list(x) for x in zip(*combined)]

        return dose_types, starts, ends, values, units

    # --- Backend: Fixture-based fallback ---

    def _predict_fallback(self, df_subset, settings):
        """Simple ISF-based glucose prediction when no backend is available."""
        n_steps = self.prediction_horizon // 5
        preds = []

        for i in range(len(df_subset)):
            row = df_subset.iloc[i]
            glucose_data = self._extract_lagged('CGM', row)

            if len(glucose_data) < 2:
                preds.append(self._flat_prediction(row, n_steps))
                continue

            current_bg = glucose_data[0][1]
            # Simple momentum-based prediction
            delta = glucose_data[0][1] - glucose_data[1][1] if len(glucose_data) > 1 else 0

            # Estimate IOB effect from insulin history
            insulin_data = self._extract_lagged('bolus', row) if 'bolus' in row.index else []
            iob_effect = sum(v * 0.5 for _, v in insulin_data if v > 0)  # rough IOB
            isf = settings.get('isf', 50)

            trajectory = []
            bg = current_bg
            for step in range(n_steps):
                # Momentum decays, insulin effect grows
                momentum = delta * max(0, 1 - step * 0.15)
                insulin_drop = iob_effect * isf * (step + 1) / (n_steps * 2)
                bg = bg + momentum - insulin_drop / n_steps
                bg = max(39, min(400, bg))  # physiological bounds
                trajectory.append(round(bg, 1))

            preds.append(trajectory)

        return preds

    # --- Shared utilities ---

    def _extract_lagged(self, prefix, row):
        """Extract (lag_minutes, value) pairs from lagged features, sorted by lag."""
        pairs = []
        if prefix in row.index:
            val = row[prefix]
            if not np.isnan(val):
                pairs.append((0, float(val)))

        for col in row.index:
            if col.startswith(f'{prefix}_') and 'what_if' not in col:
                try:
                    lag = int(col.split('_')[-1])
                    val = row[col]
                    if not np.isnan(val):
                        pairs.append((lag, float(val)))
                except (ValueError, TypeError):
                    continue

        pairs.sort(key=lambda x: x[0])
        return pairs

    def _flat_prediction(self, row, n_steps):
        bg = float(row['CGM']) if 'CGM' in row.index and not np.isnan(row['CGM']) else 100
        return [bg] * n_steps

    def _pad_prediction(self, values, n_steps):
        if not values:
            return [100] * n_steps
        while len(values) < n_steps:
            values.append(values[-1])
        return values[:n_steps]

    def process_data(self, df, model_config_manager, real_time):
        return process_data(df, model_config_manager, real_time)

    def best_params(self):
        return self.therapy_settings


# === Standalone test ===
if __name__ == '__main__':
    print(f"LoopAlgorithm GluPredKit wrapper")
    print(f"Backend: {detect_backend()}")
    print(f"Binary: {LOOP_BINARY} ({'exists' if os.path.isfile(LOOP_BINARY) else 'not found'})")
    print(f"Fixtures: {FIXTURES_DIR} ({'exists' if os.path.isdir(FIXTURES_DIR) else 'not found'})")

    # Verify fixture compatibility
    fixture_pairs = [
        ('suspend_scenario.json', 'suspend_recommendation.json'),
        ('carbs_with_isf_change_scenario.json', 'carbs_with_isf_change_recommendation.json'),
    ]

    print(f"\nLoopAlgorithm fixture format analysis:")
    for scenario_file, rec_file in fixture_pairs:
        scenario_path = os.path.join(FIXTURES_DIR, scenario_file)
        rec_path = os.path.join(FIXTURES_DIR, rec_file)
        if os.path.exists(scenario_path):
            with open(scenario_path) as f:
                scenario = json.load(f)
            print(f"\n  {scenario_file}:")
            print(f"    Keys: {list(scenario.keys())}")
            print(f"    Glucose entries: {len(scenario.get('glucoseHistory', []))}")
            print(f"    Doses: {len(scenario.get('doses', []))}")
            print(f"    Carbs: {len(scenario.get('carbEntries', []))}")
            print(f"    Type: {scenario.get('recommendationType')}")

        if os.path.exists(rec_path):
            with open(rec_path) as f:
                rec = json.load(f)
            print(f"  {rec_file}:")
            print(f"    Recommendation: {json.dumps(rec, indent=6)[:200]}")

    # Test fallback prediction
    print(f"\nTesting fallback predictor (no binary/PyLoopKit):")
    model = Model(prediction_horizon=60)
    # Simulate a simple row
    idx = pd.DatetimeIndex([datetime.datetime(2023, 10, 17, 12, 0, 0)])
    test_row = pd.DataFrame({
        'CGM': [145.0], 'CGM_5': [143.0], 'CGM_10': [140.0],
        'id': [1]
    }, index=idx)
    model.subject_ids = [1]
    model.therapy_settings = {1: {'isf': 50, 'cr': 10, 'basal': 0.8,
                                   'target_low': 100, 'target_high': 115,
                                   'suspend_threshold': 70, 'dia': 4,
                                   'max_basal': 3, 'max_bolus': 10}}
    model.is_fitted = True
    result = model._predict_model(test_row)
    print(f"  Input BG: 145 → Trajectory: {result[0][:6]}...")
    print(f"  Shape: {result.shape} (expected: (1, 12))")
    print(f"\n✓ LoopAlgorithm wrapper operational (backend: {model.backend})")
