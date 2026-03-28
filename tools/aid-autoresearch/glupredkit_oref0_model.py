"""
oref0 GluPredKit BaseModel Wrapper

Wraps OpenAPS oref0 determine-basal algorithm as a GluPredKit-compatible model.
Uses Node.js subprocess to call the oref0 library for glucose trajectory predictions.

Usage:
    glupredkit train_model config.json --model-path /path/to/glupredkit_oref0_model.py

The model:
  - _fit_model(): Estimates therapy settings (ISF, CR, basal) from training data
    using the 1800/500 rules with grid-search optimization.
  - _predict_model(): For each test row, reconstructs glucose/insulin/carb history
    from lagged + what-if features, calls oref0 via oref0_predict.js, and returns
    predicted glucose trajectories.

Trace: ALG-VERIFY-003, REQ-060
"""

import os
import sys
import json
import subprocess
import tempfile
import datetime
import numpy as np
import pandas as pd

# Add GluPredKit to path if not installed
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
GLUPREDKIT_DIR = os.path.join(REPO_ROOT, 'externals', 'GluPredKit')
if GLUPREDKIT_DIR not in sys.path:
    sys.path.insert(0, GLUPREDKIT_DIR)

from glupredkit.models.base_model import BaseModel
from glupredkit.helpers.scikit_learn import process_data

OREF0_PREDICT_JS = os.path.join(SCRIPT_DIR, 'oref0_predict.js')


class Model(BaseModel):
    """oref0 determine-basal wrapped as a GluPredKit prediction model."""

    def __init__(self, prediction_horizon):
        super().__init__(prediction_horizon)
        self.subject_ids = None
        self.therapy_settings = {}  # per-subject: {isf, cr, basal, target_bg, dia, max_basal, max_iob}
        self.batch_size = 50  # requests per subprocess call (avoids huge stdin)

    def _fit_model(self, x_train, y_train, n_cross_val_samples=500, *args, **kwargs):
        """
        Estimate therapy settings from training data.

        Uses the standard 1800/500 rules to derive ISF and CR from total daily
        insulin, then grid-searches multiplier factors to minimize RMSE on a
        cross-validation sample.
        """
        required_columns = ['CGM']
        missing = [c for c in required_columns if c not in x_train.columns]
        if missing:
            raise ValueError(f"oref0 model requires columns: {', '.join(missing)}")

        self.subject_ids = x_train['id'].unique()

        # Check if insulin columns exist
        has_bolus = 'bolus' in x_train.columns
        has_basal = 'basal' in x_train.columns
        has_insulin = 'insulin' in x_train.columns

        target_col = f'target_{self.prediction_horizon}'

        for subject_id in self.subject_ids:
            x_sub = x_train[x_train['id'] == subject_id].copy()
            y_sub = y_train[x_train['id'] == subject_id]

            # Calculate total daily insulin
            if has_bolus and has_basal:
                x_sub['_total_insulin'] = x_sub['bolus'] + (x_sub['basal'] / 12)
            elif has_insulin:
                x_sub['_total_insulin'] = x_sub['insulin']
            elif has_basal:
                x_sub['_total_insulin'] = x_sub['basal'] / 12
            else:
                x_sub['_total_insulin'] = 0.5  # fallback: assume ~24U/day

            daily_insulin = x_sub.groupby(pd.Grouper(freq='D')).agg({'_total_insulin': 'sum'})
            daily_avg = np.mean(daily_insulin['_total_insulin'])
            daily_avg = max(daily_avg, 5.0)  # safety floor

            # Derive initial settings from rules of thumb
            isf = 1800 / daily_avg       # ISF via 1800 rule (mg/dL per U)
            cr = 500 / daily_avg          # CR via 500 rule (g per U)
            basal = daily_avg * 0.45 / 24  # 45% of TDI as hourly basal

            # Average basal from data if available
            if has_basal:
                avg_basal = x_sub['basal'].mean()
                if avg_basal > 0:
                    basal = avg_basal

            # Grid search for best multiplier factors
            sample_n = min(n_cross_val_samples, len(x_sub))
            if sample_n > 0 and target_col in y_sub.columns:
                sample_idx = x_sub.sample(n=sample_n, random_state=42).index
                x_sample = x_sub.loc[sample_idx]
                y_sample = y_sub.loc[sample_idx][target_col]

                mult_factors = [0.7, 0.85, 1.0, 1.15, 1.3]
                best_rmse = np.inf
                best_isf, best_cr = isf, cr

                for fi in mult_factors:
                    for fj in mult_factors:
                        test_isf = isf * fi
                        test_cr = cr * fj
                        try:
                            preds = self._batch_predict(
                                x_sample, test_isf, test_cr, basal
                            )
                            if len(preds) > 0:
                                # Use last prediction point as the horizon prediction
                                last_preds = [p[-1] if len(p) > 0 else x_sample.iloc[i]['CGM']
                                              for i, p in enumerate(preds)]
                                valid = [(t, p) for t, p in zip(y_sample.values, last_preds)
                                         if not np.isnan(t) and not np.isnan(p)]
                                if len(valid) > 10:
                                    y_t, y_p = zip(*valid)
                                    rmse = np.sqrt(np.mean((np.array(y_t) - np.array(y_p)) ** 2))
                                    if rmse < best_rmse:
                                        best_rmse = rmse
                                        best_isf, best_cr = test_isf, test_cr
                        except Exception as e:
                            print(f"Grid search error (ISF×{fi}, CR×{fj}): {e}")
                            continue

                isf, cr = best_isf, best_cr
                print(f"Subject {subject_id}: best ISF={isf:.1f}, CR={cr:.1f}, "
                      f"basal={basal:.2f}, RMSE={best_rmse:.1f}")
            else:
                print(f"Subject {subject_id}: using defaults ISF={isf:.1f}, CR={cr:.1f}, basal={basal:.2f}")

            self.therapy_settings[subject_id] = {
                'isf': isf,
                'cr': cr,
                'basal': basal,
                'target_bg': 110,
                'dia': 4,
                'max_basal': max(basal * 4, 3.0),
                'max_iob': max(daily_avg * 0.3, 3.0)
            }

        return self

    def _predict_model(self, x_test):
        """
        Generate glucose prediction trajectories for each test row.

        Returns: numpy array of shape (n_samples, prediction_horizon // 5)
        """
        y_pred = []

        for subject_id in self.subject_ids:
            df_subset = x_test[x_test['id'] == subject_id]
            settings = self.therapy_settings.get(subject_id, self.therapy_settings.get(self.subject_ids[0]))

            predictions = self._batch_predict(df_subset, settings['isf'], settings['cr'], settings['basal'],
                                              full_settings=settings)
            y_pred.extend(predictions)

        return np.array(y_pred)

    def _batch_predict(self, df_subset, isf, cr, basal, full_settings=None):
        """
        Call oref0_predict.js in batches for a DataFrame subset.
        Returns list of prediction trajectories.
        """
        if full_settings is None:
            full_settings = {
                'isf': isf, 'cr': cr, 'basal': basal,
                'target_bg': 110, 'dia': 4, 'max_basal': 3.0, 'max_iob': 5.0
            }

        n_steps = self.prediction_horizon // 5
        all_preds = []

        # Build request batch
        requests = []
        for i in range(len(df_subset)):
            row = df_subset.iloc[i]
            req = self._row_to_request(row, full_settings)
            requests.append(req)

        # Process in batches
        for batch_start in range(0, len(requests), self.batch_size):
            batch = requests[batch_start:batch_start + self.batch_size]
            results = self._call_oref0(batch)
            all_preds.extend(results)

        # Ensure correct trajectory length
        padded = []
        for pred in all_preds:
            if len(pred) >= n_steps:
                padded.append(pred[:n_steps])
            else:
                # Pad with last value
                last = pred[-1] if pred else 100
                padded.append(pred + [last] * (n_steps - len(pred)))

        return padded

    def _row_to_request(self, row, settings):
        """Convert a preprocessed DataFrame row to an oref0 prediction request."""
        # Extract glucose history from CGM + lagged features (newest-first)
        glucose = self._extract_lagged_values('CGM', row)

        # Extract insulin history from bolus + basal lagged features
        insulin = self._extract_lagged_values('bolus', row, oldest_first=True) if 'bolus' in row.index else []
        basal_hist = self._extract_lagged_values('basal', row, oldest_first=True) if 'basal' in row.index else []

        # Extract carb history
        carbs = self._extract_lagged_values('carbs', row, oldest_first=True) if 'carbs' in row.index else []

        return {
            'glucose': glucose,
            'insulin': insulin,
            'basal': basal_hist,
            'carbs': carbs,
            'profile': settings,
            'prediction_horizon': self.prediction_horizon
        }

    def _extract_lagged_values(self, prefix, row, oldest_first=False):
        """
        Extract time-lagged feature values from a row.

        For CGM: returns [CGM, CGM_5, CGM_10, ...] (newest-first by default)
        For others: returns values sorted oldest-first if requested.
        """
        values = []
        # Current value
        if prefix in row.index and not np.isnan(row[prefix]):
            values.append((0, float(row[prefix])))

        # Lagged values (CGM_5, CGM_10, etc.)
        for col in row.index:
            if col.startswith(f'{prefix}_') and 'what_if' not in col:
                try:
                    lag_min = int(col.split('_')[-1])
                    val = row[col]
                    if not np.isnan(val):
                        values.append((lag_min, float(val)))
                except (ValueError, TypeError):
                    continue

        # What-if (future) values
        for col in row.index:
            if col.startswith(f'{prefix}_what_if_'):
                try:
                    future_min = int(col.split('_')[-1])
                    val = row[col]
                    if not np.isnan(val):
                        values.append((-future_min, float(val)))  # negative = future
                except (ValueError, TypeError):
                    continue

        if not values:
            return []

        # Sort by time: for glucose (newest-first), for insulin/carbs (oldest-first)
        values.sort(key=lambda x: x[0], reverse=not oldest_first)
        return [v[1] for v in values]

    def _call_oref0(self, requests):
        """Call oref0_predict.js via subprocess with a batch of requests."""
        n_steps = self.prediction_horizon // 5

        try:
            proc = subprocess.run(
                ['node', OREF0_PREDICT_JS],
                input=json.dumps(requests),
                capture_output=True,
                text=True,
                timeout=120
            )

            if proc.returncode != 0:
                print(f"oref0_predict.js error: {proc.stderr[:200]}")
                return [self._fallback_prediction(req, n_steps) for req in requests]

            results = json.loads(proc.stdout)
            return results

        except subprocess.TimeoutExpired:
            print("oref0_predict.js timeout (120s)")
            return [self._fallback_prediction(req, n_steps) for req in requests]
        except json.JSONDecodeError as e:
            print(f"oref0_predict.js JSON decode error: {e}")
            return [self._fallback_prediction(req, n_steps) for req in requests]
        except Exception as e:
            print(f"oref0_predict.js exception: {e}")
            return [self._fallback_prediction(req, n_steps) for req in requests]

    def _fallback_prediction(self, request, n_steps):
        """Flat-line prediction when oref0 fails."""
        bg = request.get('glucose', [100])[0] if request.get('glucose') else 100
        return [bg] * n_steps

    def process_data(self, df, model_config_manager, real_time):
        """Use standard scikit-learn feature engineering pipeline."""
        return process_data(df, model_config_manager, real_time)

    def best_params(self):
        """Return fitted therapy settings per subject."""
        return self.therapy_settings


# === Standalone test ===
if __name__ == '__main__':
    """Quick smoke test using a TV-* conformance vector."""
    import glob

    vectors_dir = os.path.join(REPO_ROOT, 'conformance', 't1pal', 'vectors', 'oref0-endtoend')
    vector_files = sorted(glob.glob(os.path.join(vectors_dir, 'TV-*.json')))

    if not vector_files:
        print("No TV-* vectors found. Run from repo root.")
        sys.exit(1)

    # Load first 5 vectors
    n_test = min(5, len(vector_files))
    print(f"Testing oref0 GluPredKit wrapper with {n_test} vectors...")

    requests = []
    for vf in vector_files[:n_test]:
        with open(vf) as f:
            vec = json.load(f)
        inp = vec['input']

        # Build a simplified request from vector format
        glucose = [inp['glucoseStatus']['glucose']]
        if 'delta' in inp['glucoseStatus']:
            glucose.append(inp['glucoseStatus']['glucose'] - inp['glucoseStatus']['delta'])

        req = {
            'glucose': glucose,
            'insulin': [],
            'basal': [],
            'carbs': [],
            'profile': {
                'isf': inp['profile'].get('sensitivity', 50),
                'cr': inp['profile'].get('carbRatio', 10),
                'basal': inp['profile'].get('basalRate', inp['profile'].get('currentBasal', 0.8)),
                'target_bg': ((inp['profile'].get('targetLow', 100) + inp['profile'].get('targetHigh', 110)) / 2),
                'dia': inp['profile'].get('dia', 4),
                'max_basal': inp['profile'].get('maxBasal', 3.0),
                'max_iob': inp['profile'].get('maxIob', 5.0)
            },
            'prediction_horizon': 60
        }
        requests.append(req)

    # Call oref0
    proc = subprocess.run(
        ['node', OREF0_PREDICT_JS],
        input=json.dumps(requests),
        capture_output=True,
        text=True,
        timeout=30
    )

    if proc.returncode != 0:
        print(f"ERROR: {proc.stderr}")
        sys.exit(1)

    results = json.loads(proc.stdout)
    for i, (vf, traj) in enumerate(zip(vector_files[:n_test], results)):
        name = os.path.basename(vf)
        with open(vf) as f:
            vec = json.load(f)
        bg = vec['input']['glucoseStatus']['glucose']
        exp_bg = vec['expected'].get('eventualBG', '?')
        print(f"  {name}: BG={bg} → trajectory={traj[:4]}... (expected eventualBG={exp_bg})")

    print(f"\n✓ oref0 wrapper produced {len(results)} trajectories, "
          f"each with {len(results[0])} steps (5-min intervals, {len(results[0])*5}min horizon)")
