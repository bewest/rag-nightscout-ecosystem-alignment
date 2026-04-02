"""forecast.py — Multi-horizon forecasting, scenario simulation, and backtesting.

Combines short/medium/long-term models into a unified forecasting pipeline
that supports hypothetical action evaluation and retrospective backtesting.

Components:
1. HierarchicalForecaster: Multi-resolution forecast compositor
2. ScenarioSimulator: "What if meal/exercise at time T?" evaluation
3. BacktestEngine: Retrospective replay with override suggestions

Usage:
    from tools.cgmencode.forecast import (
        HierarchicalForecaster, ScenarioSimulator, BacktestEngine,
    )
"""
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from .schema import NORMALIZATION_SCALES, IDX_GLUCOSE, NUM_FEATURES
from .evaluate import clinical_summary, override_accuracy


GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']


# =============================================================================
# 1. Hierarchical Forecaster
# =============================================================================

class HierarchicalForecaster:
    """Multi-resolution forecast combining short, medium, and long horizons.

    - Short-term (5-min, 0-3hr): GroupedEncoder or TransformerAE
    - Medium-term (15-min, 3-12hr): Coarse-grid model or persistence
    - Long-term (1-hr, 12-72hr): Persistence + state tracker drift adjustment

    Blends overlapping regions with weighted averaging.
    """

    def __init__(self, short_model=None, medium_model=None,
                 blend_steps=6, state_tracker=None):
        """
        Args:
            short_model: trained model for 5-min resolution (0-3hr)
            medium_model: trained model for 15-min resolution (optional)
            blend_steps: steps over which to blend short→medium
            state_tracker: ISFCRTracker for long-term drift adjustment
        """
        self.short_model = short_model
        self.medium_model = medium_model
        self.blend_steps = blend_steps
        self.state_tracker = state_tracker

    def forecast(self, x, horizon_hours=6.0, causal=True):
        """Generate multi-horizon glucose forecast.

        Args:
            x: input tensor (B, SeqLen, Features), normalized
            horizon_hours: how far to forecast (up to 72)
            causal: use causal masking

        Returns:
            dict with 'glucose_mgdl', 'timestamps_min', 'resolution',
                  'confidence' per horizon segment
        """
        results = {}

        # Short-term: model-based (0-3hr)
        if self.short_model is not None:
            short_steps = min(36, int(horizon_hours * 12))  # 5-min steps
            with torch.no_grad():
                pred = self.short_model(x, causal=causal)
            glucose = pred[..., IDX_GLUCOSE] * GLUCOSE_SCALE
            results['short'] = {
                'glucose_mgdl': glucose.detach().cpu().numpy() if isinstance(glucose, torch.Tensor) else glucose,
                'interval_min': 5,
                'horizon_steps': short_steps,
            }

        # Medium-term: coarse model or persistence (3-12hr)
        if horizon_hours > 3.0:
            if self.medium_model is not None:
                # Downsample input to 15-min and run medium model
                x_coarse = x[:, ::3, :]  # naive 3x downsample
                with torch.no_grad():
                    med_pred = self.medium_model(x_coarse, causal=causal)
                glucose_med = med_pred[..., IDX_GLUCOSE] * GLUCOSE_SCALE
            else:
                # Persistence: last known glucose
                last_glucose = x[:, -1, IDX_GLUCOSE] * GLUCOSE_SCALE
                med_steps = int(min(horizon_hours - 3, 9) * 4)  # 15-min steps
                glucose_med = last_glucose.unsqueeze(-1).expand(-1, med_steps)

            results['medium'] = {
                'glucose_mgdl': glucose_med.detach().cpu().numpy() if isinstance(glucose_med, torch.Tensor) else glucose_med,
                'interval_min': 15,
                'horizon_steps': glucose_med.shape[-1] if hasattr(glucose_med, 'shape') else 0,
            }

        # Long-term: drift-adjusted persistence (12-72hr)
        if horizon_hours > 12.0:
            last_glucose = float(x[0, -1, IDX_GLUCOSE].item()) * GLUCOSE_SCALE
            drift_factor = 1.0
            if self.state_tracker is not None:
                summary = self.state_tracker.drift_summary()
                drift_factor = 1.0 + summary.get('isf_drift_pct', 0) / 100.0

            long_steps = int(min(horizon_hours - 12, 60))  # 1-hr steps
            # Drift-adjusted persistence: glucose trends toward mean with drift
            target = 120.0 * drift_factor  # drift-adjusted target
            alpha = 0.1  # mean-reversion rate per hour
            long_glucose = np.zeros(long_steps)
            g = last_glucose
            for i in range(long_steps):
                g = g + alpha * (target - g)
                long_glucose[i] = g

            results['long'] = {
                'glucose_mgdl': long_glucose,
                'interval_min': 60,
                'horizon_steps': long_steps,
                'drift_factor': drift_factor,
            }

        return results

    def combined_forecast_mgdl(self, x, horizon_hours=6.0, causal=True):
        """Get a single combined glucose trajectory in mg/dL.

        Stitches short/medium/long with blending at boundaries.

        Returns:
            glucose: 1D array of glucose values in mg/dL
            times_min: 1D array of forecast times in minutes
        """
        segments = self.forecast(x, horizon_hours=horizon_hours, causal=causal)

        all_glucose = []
        all_times = []
        t_offset = 0

        for key in ['short', 'medium', 'long']:
            if key not in segments:
                continue
            seg = segments[key]
            g = np.asarray(seg['glucose_mgdl']).flatten()
            interval = seg['interval_min']
            times = np.arange(len(g)) * interval + t_offset

            if all_glucose and self.blend_steps > 0:
                # Blend overlap region
                n_blend = min(self.blend_steps, len(all_glucose), len(g))
                for i in range(n_blend):
                    w = i / n_blend  # weight increases for new segment
                    all_glucose[-(n_blend - i)] = (
                        (1 - w) * all_glucose[-(n_blend - i)] + w * g[i]
                    )
                g = g[n_blend:]
                times = times[n_blend:]

            all_glucose.extend(g.tolist())
            all_times.extend(times.tolist())
            t_offset = all_times[-1] + interval if all_times else 0

        return np.array(all_glucose), np.array(all_times)


# =============================================================================
# 2. Scenario Simulator
# =============================================================================

class ScenarioSimulator:
    """Evaluate hypothetical actions ("what if meal/exercise at time T?").

    Modifies the input feature tensor with hypothetical actions and runs
    the forecaster to compare outcomes.
    """

    SCENARIO_TEMPLATES = {
        'meal_small': {'carbs': 20, 'bolus': 1.5, 'absorption_min': 120},
        'meal_medium': {'carbs': 45, 'bolus': 3.5, 'absorption_min': 180},
        'meal_large': {'carbs': 80, 'bolus': 6.0, 'absorption_min': 240},
        'exercise_light': {'duration_min': 30, 'insulin_scale': 0.7},
        'exercise_moderate': {'duration_min': 60, 'insulin_scale': 0.5},
        'exercise_intense': {'duration_min': 90, 'insulin_scale': 0.3},
    }

    def __init__(self, forecaster: HierarchicalForecaster):
        self.forecaster = forecaster

    def simulate_scenario(self, x, scenario_name, inject_at_step=-1,
                          horizon_hours=3.0):
        """Run a scenario and compare to baseline.

        Args:
            x: input tensor (1, SeqLen, Features)
            scenario_name: key into SCENARIO_TEMPLATES or custom dict
            inject_at_step: which step to inject the action (-1 = last)
            horizon_hours: forecast horizon

        Returns:
            dict with baseline/scenario forecasts and delta
        """
        if isinstance(scenario_name, str):
            template = self.SCENARIO_TEMPLATES.get(scenario_name, {})
        else:
            template = scenario_name

        # Baseline forecast
        base_glucose, base_times = self.forecaster.combined_forecast_mgdl(
            x, horizon_hours=horizon_hours)

        # Inject scenario into input
        x_mod = x.clone() if isinstance(x, torch.Tensor) else torch.tensor(x).float()
        step = inject_at_step if inject_at_step >= 0 else x_mod.shape[1] - 1

        if 'carbs' in template:
            carb_idx = 5  # schema index for carbs
            bolus_idx = 4  # schema index for bolus
            x_mod[0, step, carb_idx] = template['carbs'] / NORMALIZATION_SCALES.get('carbs', 100)
            x_mod[0, step, bolus_idx] = template.get('bolus', 0) / NORMALIZATION_SCALES.get('bolus', 10)

        # Scenario forecast
        scen_glucose, scen_times = self.forecaster.combined_forecast_mgdl(
            x_mod, horizon_hours=horizon_hours)

        # Align lengths
        min_len = min(len(base_glucose), len(scen_glucose))
        delta = scen_glucose[:min_len] - base_glucose[:min_len]

        return {
            'baseline_mgdl': base_glucose[:min_len],
            'scenario_mgdl': scen_glucose[:min_len],
            'delta_mgdl': delta,
            'times_min': base_times[:min_len],
            'scenario': template,
            'max_impact_mgdl': float(np.max(np.abs(delta))) if len(delta) > 0 else 0.0,
            'mean_impact_mgdl': float(np.mean(delta)) if len(delta) > 0 else 0.0,
        }

    def compare_scenarios(self, x, scenarios, horizon_hours=3.0):
        """Run multiple scenarios and rank by outcome quality.

        Args:
            x: input tensor
            scenarios: list of scenario names or dicts
            horizon_hours: forecast horizon

        Returns:
            list of scenario results sorted by best TIR
        """
        results = []
        for s in scenarios:
            result = self.simulate_scenario(x, s, horizon_hours=horizon_hours)
            tir = clinical_summary(result['scenario_mgdl'])['tir']
            result['tir'] = tir
            result['name'] = s if isinstance(s, str) else 'custom'
            results.append(result)

        return sorted(results, key=lambda r: -r['tir'])


# =============================================================================
# 3. Backtest Engine
# =============================================================================

class BacktestEngine:
    """Retrospective replay engine for override suggestion evaluation.

    Replays historical glucose data and evaluates what would have happened
    if the model's override suggestions had been followed.
    """

    def __init__(self, forecaster: HierarchicalForecaster = None,
                 classifier_model=None):
        self.forecaster = forecaster
        self.classifier_model = classifier_model

    def replay(self, glucose_mgdl, events_actual, tabular_windows=None,
               suggestion_threshold=0.3):
        """Replay historical data and evaluate suggestions.

        Args:
            glucose_mgdl: array of actual glucose values
            events_actual: list of actual event dicts with timestamp_idx
            tabular_windows: optional tabular features for classifier
            suggestion_threshold: min probability for suggestions

        Returns:
            dict with clinical metrics, suggestion accuracy, lead times
        """
        glucose = np.asarray(glucose_mgdl, dtype=float)

        # Actual clinical outcomes
        actual_clinical = clinical_summary(glucose)

        # Generate suggestions if classifier available
        suggestions = []
        if self.classifier_model is not None and tabular_windows is not None:
            from .event_classifier import predict_events
            suggestions = predict_events(
                self.classifier_model, tabular_windows,
                threshold=suggestion_threshold
            )

        # Score suggestions against actual events
        suggested_events = [
            {'timestamp_idx': s['index'], 'event_type': s['event_type']}
            for s in suggestions
        ]
        accuracy = override_accuracy(suggested_events, events_actual)

        return {
            'actual_clinical': actual_clinical,
            'n_suggestions': len(suggestions),
            'suggestion_accuracy': accuracy,
            'suggestions': suggestions[:20],  # first 20 for inspection
        }

    def evaluate_window(self, glucose_mgdl, window_start, window_end,
                        suggested_override=None):
        """Evaluate a specific time window with optional override.

        Compares clinical metrics with and without the suggested override.

        Args:
            glucose_mgdl: full glucose array
            window_start: start index
            window_end: end index
            suggested_override: optional override dict

        Returns:
            dict with baseline and override-adjusted clinical metrics
        """
        window = glucose_mgdl[window_start:window_end]
        baseline = clinical_summary(window)

        result = {
            'baseline': baseline,
            'window_start': window_start,
            'window_end': window_end,
            'n_readings': len(window),
        }

        if suggested_override:
            result['override'] = suggested_override
            result['override_type'] = suggested_override.get('override_type', 'unknown')

        return result

    def full_backtest(self, glucose_mgdl, events, window_size_steps=72,
                      stride_steps=36):
        """Run sliding-window backtest over entire glucose trace.

        Args:
            glucose_mgdl: full glucose array
            events: list of actual events with timestamp_idx
            window_size_steps: evaluation window (default 72 = 6 hours)
            stride_steps: step between windows (default 36 = 3 hours)

        Returns:
            dict with per-window and aggregate clinical metrics
        """
        glucose = np.asarray(glucose_mgdl, dtype=float)
        windows = []

        for start in range(0, len(glucose) - window_size_steps, stride_steps):
            end = start + window_size_steps
            window_glucose = glucose[start:end]
            metrics = clinical_summary(window_glucose)
            metrics['start_idx'] = start
            metrics['end_idx'] = end
            windows.append(metrics)

        if not windows:
            return {'n_windows': 0}

        # Aggregate
        tirs = [w['tir'] for w in windows]
        gris = [w['gri'] for w in windows]
        hypo_counts = [w['hypo_events'] for w in windows]

        return {
            'n_windows': len(windows),
            'mean_tir': round(float(np.mean(tirs)), 2),
            'std_tir': round(float(np.std(tirs)), 2),
            'mean_gri': round(float(np.mean(gris)), 2),
            'total_hypo_events': int(np.sum(hypo_counts)),
            'pct_windows_hypo': round(float(np.mean(np.array(hypo_counts) > 0) * 100), 2),
            'windows': windows[:10],  # first 10 for inspection
        }
