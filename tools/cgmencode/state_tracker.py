"""
state_tracker.py — Bayesian ISF/CR drift tracker using Kalman filtering.

Tracks effective insulin sensitivity factor (ISF) and carb ratio (CR) over
time by observing the discrepancy between physics-predicted and actual glucose.
Detects when these parameters drift significantly, indicating illness,
hormonal changes, or other physiological shifts.

Addresses GAP-ML-006: no runtime detection of ISF/CR drift across AID systems.

The physics model says:
    Δglucose ≈ -ΔIOB × ISF + ΔCOB × (ISF / CR)

If actual glucose deviates from prediction (positive residual when ISF is
overestimated), the Kalman filter adjusts ISF and CR estimates to explain
the residual.

Usage:
    from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector

    tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
    for window in patient_windows:
        state = tracker.update(glucose_residual, iob_delta, cob_delta)
        if state['isf_drift_pct'] > 20:
            print(f"ISF drift detected: {state['isf_drift_pct']:.0f}%")

    detector = DriftDetector(tracker)
    classification = detector.classify()
    override = detector.suggested_override()
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .schema import NORMALIZATION_SCALES


class ISFCRTracker:
    """Track effective ISF and CR using a 2-state Kalman filter.

    State vector: x = [ISF, CR]
    Observation: glucose_residual = actual - physics_predicted (mg/dL)

    The physics model predicts:
        Δglucose ≈ -ΔIOB × ISF + ΔCOB × (ISF / CR)

    The observation model linearizes the residual w.r.t. the state:
        residual ≈ H @ (x - x_nominal)
    where H is the Jacobian of the residual w.r.t. [ISF, CR].

    Uses the Joseph form for the covariance update to ensure numerical
    stability (P stays symmetric positive-definite even with roundoff).
    """

    def __init__(self, nominal_isf: float = 40.0, nominal_cr: float = 10.0,
                 process_noise: float = 0.01, measurement_noise: float = 5.0):
        """
        Args:
            nominal_isf: Baseline ISF from patient profile (mg/dL per U).
            nominal_cr: Baseline CR from patient profile (g per U).
            process_noise: How fast we expect ISF/CR to drift (per step).
                Larger values make the filter more responsive but noisier.
            measurement_noise: CGM noise variance (mg/dL²).
        """
        if nominal_isf <= 0:
            raise ValueError(f"nominal_isf must be positive, got {nominal_isf}")
        if nominal_cr <= 0:
            raise ValueError(f"nominal_cr must be positive, got {nominal_cr}")

        # State: [ISF, CR]
        self.state = np.array([nominal_isf, nominal_cr], dtype=np.float64)
        self.nominal = np.array([nominal_isf, nominal_cr], dtype=np.float64)

        # Covariance matrix — initial uncertainty
        self.P = np.eye(2, dtype=np.float64) * 10.0

        # Process noise covariance (drives drift allowance)
        self.Q = np.eye(2, dtype=np.float64) * process_noise

        # Measurement noise variance (scalar — single observation per step)
        self.R = float(measurement_noise)

        # History for drift detection and retrospective analysis
        self.history: List[Dict] = []

    def _observation_jacobian(self, iob_delta: float, cob_delta: float) -> np.ndarray:
        """Linearized observation matrix H.

        The physics prediction using the *nominal* parameters is:
            pred_nominal = ... - ΔIOB × ISF_nom + ΔCOB × (ISF_nom / CR_nom)

        With *true* parameters [ISF, CR]:
            pred_true = ... - ΔIOB × ISF + ΔCOB × (ISF / CR)

        The residual (actual - pred_nominal) is approximately:
            residual ≈ -ΔIOB × (ISF_nom - ISF) + ΔCOB × (ISF_nom/CR_nom - ISF/CR)

        But we track the *absolute* state, not the deviation. The observation
        model for the Kalman filter relates the predicted observation to state:
            z_predicted = -ΔIOB × ISF + ΔCOB × (ISF / CR)
            (this is the physics-predicted glucose *change* using current state)

        Partial derivatives (Jacobian H):
            ∂z/∂ISF = -ΔIOB + ΔCOB / CR
            ∂z/∂CR  = -ΔCOB × ISF / CR²

        Returns:
            H: (1, 2) observation Jacobian
        """
        isf, cr = self.state
        cr_sq = cr * cr + 1e-12  # avoid division by zero

        h_isf = -iob_delta + cob_delta / (cr + 1e-12)
        h_cr = -cob_delta * isf / cr_sq

        return np.array([[h_isf, h_cr]], dtype=np.float64)

    def predict(self) -> None:
        """Kalman predict step: propagate state and covariance forward.

        State transition is identity (ISF/CR are slowly varying).
        """
        # x_pred = F @ x, with F = I → x unchanged
        # P_pred = F @ P @ F^T + Q → P + Q
        self.P = self.P + self.Q

    def update(self, glucose_residual: float, iob_delta: float,
               cob_delta: float, timestamp=None) -> Dict:
        """Process one observation and update ISF/CR estimates.

        Args:
            glucose_residual: actual_glucose - physics_predicted (mg/dL).
            iob_delta: Change in IOB over this step (Units).
                Positive means IOB increased (insulin delivered).
            cob_delta: Change in COB over this step (grams).
                Positive means COB increased (carbs eaten).
            timestamp: Optional timestamp for history tracking.

        Returns:
            dict with: isf, cr, isf_drift_pct, cr_drift_pct,
                      isf_uncertainty, cr_uncertainty, timestamp
        """
        # --- Predict step ---
        self.predict()

        # --- Check observability ---
        # If both deltas are near zero, we have no information about ISF/CR.
        # Skip the measurement update to avoid numerical issues.
        info_magnitude = abs(iob_delta) + abs(cob_delta)
        if info_magnitude < 1e-6:
            return self._build_result(timestamp)

        # --- Observation model ---
        H = self._observation_jacobian(iob_delta, cob_delta)

        # Predicted observation: what the current state predicts the
        # glucose change would be (relative to nominal prediction)
        isf, cr = self.state
        z_predicted = -iob_delta * isf + cob_delta * (isf / (cr + 1e-12))

        # The nominal physics model predicted:
        #   z_nominal = -iob_delta * ISF_nom + cob_delta * (ISF_nom / CR_nom)
        isf_nom, cr_nom = self.nominal
        z_nominal = -iob_delta * isf_nom + cob_delta * (isf_nom / (cr_nom + 1e-12))

        # Innovation: how much the actual residual differs from what our
        # current state estimate would predict beyond the nominal model.
        # glucose_residual = actual - physics_predicted_with_nominal
        # The filter's predicted residual is (z_predicted - z_nominal)
        innovation = glucose_residual - (z_predicted - z_nominal)

        # --- Kalman gain ---
        # S = H @ P @ H^T + R  (scalar since single observation)
        S = float((H @ self.P @ H.T)[0, 0]) + self.R
        if abs(S) < 1e-12:
            return self._build_result(timestamp)

        K = (self.P @ H.T) / S  # (2, 1) Kalman gain

        # --- State update ---
        self.state = self.state + (K.flatten() * innovation)

        # Clamp to physiological bounds
        self.state[0] = np.clip(self.state[0], 5.0, 500.0)   # ISF: 5–500
        self.state[1] = np.clip(self.state[1], 1.0, 100.0)   # CR: 1–100

        # --- Covariance update (Joseph form for numerical stability) ---
        # P = (I - K @ H) @ P @ (I - K @ H)^T + K @ R @ K^T
        I_KH = np.eye(2) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + (K @ K.T) * self.R

        # Force symmetry (combat floating-point drift)
        self.P = 0.5 * (self.P + self.P.T)

        return self._build_result(timestamp)

    def _build_result(self, timestamp=None) -> Dict:
        """Construct result dict from current state."""
        isf, cr = self.state
        isf_nom, cr_nom = self.nominal
        isf_unc = np.sqrt(max(self.P[0, 0], 0.0))
        cr_unc = np.sqrt(max(self.P[1, 1], 0.0))

        result = {
            'isf': float(isf),
            'cr': float(cr),
            'isf_drift_pct': float(abs(isf - isf_nom) / isf_nom * 100.0),
            'cr_drift_pct': float(abs(cr - cr_nom) / cr_nom * 100.0),
            'isf_uncertainty': float(isf_unc),
            'cr_uncertainty': float(cr_unc),
            'timestamp': timestamp,
        }
        self.history.append(result)
        return result

    def drift_summary(self, window_hours: float = 72) -> Dict:
        """Summarize drift over a time window.

        If timestamps are available, uses only the most recent `window_hours`.
        Otherwise uses all history.

        Returns:
            dict with: mean_isf, mean_cr, isf_trend, cr_trend,
                      isf_drift_pct, cr_drift_pct, is_significant,
                      suggested_adjustment
        """
        if not self.history:
            return {
                'mean_isf': float(self.nominal[0]),
                'mean_cr': float(self.nominal[1]),
                'isf_trend': 0.0,
                'cr_trend': 0.0,
                'isf_drift_pct': 0.0,
                'cr_drift_pct': 0.0,
                'is_significant': False,
                'suggested_adjustment': None,
            }

        # Select observations within the time window
        entries = self.history
        if (entries[-1]['timestamp'] is not None
                and entries[0]['timestamp'] is not None):
            cutoff = entries[-1]['timestamp'] - window_hours * 3600
            entries = [e for e in entries if e['timestamp'] >= cutoff] or entries

        isf_values = np.array([e['isf'] for e in entries])
        cr_values = np.array([e['cr'] for e in entries])

        mean_isf = float(np.mean(isf_values))
        mean_cr = float(np.mean(cr_values))

        # Linear trend (slope) via least-squares
        n = len(isf_values)
        if n >= 2:
            t_idx = np.arange(n, dtype=np.float64)
            isf_trend = float(np.polyfit(t_idx, isf_values, 1)[0])
            cr_trend = float(np.polyfit(t_idx, cr_values, 1)[0])
        else:
            isf_trend = 0.0
            cr_trend = 0.0

        isf_nom, cr_nom = self.nominal
        isf_drift_pct = abs(mean_isf - isf_nom) / isf_nom * 100.0
        cr_drift_pct = abs(mean_cr - cr_nom) / cr_nom * 100.0
        is_significant = bool(isf_drift_pct > 15.0 or cr_drift_pct > 15.0)

        suggested = None
        if is_significant:
            isf_factor = isf_nom / mean_isf if mean_isf > 0 else 1.0
            cr_factor = cr_nom / mean_cr if mean_cr > 0 else 1.0
            suggested = {
                'isf_factor': float(np.clip(isf_factor, 0.5, 2.0)),
                'cr_factor': float(np.clip(cr_factor, 0.5, 2.0)),
            }

        return {
            'mean_isf': float(mean_isf),
            'mean_cr': float(mean_cr),
            'isf_trend': float(isf_trend),
            'cr_trend': float(cr_trend),
            'isf_drift_pct': float(isf_drift_pct),
            'cr_drift_pct': float(cr_drift_pct),
            'is_significant': is_significant,
            'suggested_adjustment': suggested,
        }

    def reset(self) -> None:
        """Reset tracker to nominal state."""
        self.state = self.nominal.copy()
        self.P = np.eye(2, dtype=np.float64) * 10.0
        self.history.clear()


class DriftDetector:
    """Detect physiological state changes from ISF/CR drift patterns.

    Monitors ISF/CR tracker output and classifies drift into:
    - 'stable': ISF/CR within ±threshold of nominal
    - 'resistance': ISF dropping → need more insulin (illness, hormones)
    - 'sensitivity': ISF rising → need less insulin (exercise adaptation)
    - 'carb_change': CR shifting without ISF change
    """

    # Classification thresholds
    CLASSIFICATIONS = {
        'stable': 'No significant drift detected',
        'resistance': 'Insulin resistance increasing (illness, hormones, stress)',
        'sensitivity': 'Insulin sensitivity increasing (exercise, weight loss)',
        'carb_change': 'Carb ratio shifting without ISF change',
    }

    def __init__(self, tracker: ISFCRTracker, drift_threshold_pct: float = 15.0,
                 window_hours: float = 72, min_observations: int = 12):
        """
        Args:
            tracker: ISFCRTracker instance to monitor.
            drift_threshold_pct: Percent change from nominal to consider
                significant (default 15%).
            window_hours: Hours of history to consider for classification.
            min_observations: Minimum observations before making a call.
        """
        self.tracker = tracker
        self.drift_threshold_pct = drift_threshold_pct
        self.window_hours = window_hours
        self.min_observations = min_observations

    def classify(self) -> Dict:
        """Classify current physiological state from drift patterns.

        Returns:
            dict with:
                - 'state': one of 'stable', 'resistance', 'sensitivity', 'carb_change'
                - 'description': human-readable explanation
                - 'isf_drift_pct': signed drift (negative = resistance)
                - 'cr_drift_pct': signed drift
                - 'confidence': 0–1 confidence in classification
        """
        summary = self.tracker.drift_summary(self.window_hours)
        n_obs = len(self.tracker.history)

        # Not enough data → stable by default
        if n_obs < self.min_observations:
            return {
                'state': 'stable',
                'description': self.CLASSIFICATIONS['stable'],
                'isf_drift_pct': 0.0,
                'cr_drift_pct': 0.0,
                'confidence': 0.0,
            }

        isf_nom = self.tracker.nominal[0]
        cr_nom = self.tracker.nominal[1]

        # Signed drift: negative ISF drift = ISF dropped = resistance
        isf_signed = (summary['mean_isf'] - isf_nom) / isf_nom * 100.0
        cr_signed = (summary['mean_cr'] - cr_nom) / cr_nom * 100.0

        isf_significant = abs(isf_signed) > self.drift_threshold_pct
        cr_significant = abs(cr_signed) > self.drift_threshold_pct

        # Confidence scales with observation count and drift magnitude
        confidence = min(1.0, n_obs / (self.min_observations * 3))
        if isf_significant or cr_significant:
            drift_mag = max(abs(isf_signed), abs(cr_signed))
            confidence *= min(1.0, drift_mag / (self.drift_threshold_pct * 2))

        # Classification logic
        if isf_significant and isf_signed < 0:
            state = 'resistance'
        elif isf_significant and isf_signed > 0:
            state = 'sensitivity'
        elif cr_significant and not isf_significant:
            state = 'carb_change'
        else:
            state = 'stable'

        return {
            'state': state,
            'description': self.CLASSIFICATIONS[state],
            'isf_drift_pct': float(isf_signed),
            'cr_drift_pct': float(cr_signed),
            'confidence': float(confidence),
        }

    def suggested_override(self) -> Optional[Dict]:
        """Suggest override parameters based on detected drift.

        Returns:
            None if stable, or dict with:
            - 'type': 'sick', 'exercise_recovery', 'hormone_cycle', etc.
            - 'insulin_needs_factor': e.g., 1.2 means 20% more insulin
            - 'confidence': 0–1 confidence in suggestion
            - 'duration_hours': suggested override duration
        """
        classification = self.classify()

        if classification['state'] == 'stable':
            return None

        state = classification['state']
        confidence = classification['confidence']
        summary = self.tracker.drift_summary(self.window_hours)

        # Insulin needs factor: >1 means need more insulin
        # ISF dropped → need more insulin → factor > 1
        isf_nom = self.tracker.nominal[0]
        mean_isf = summary['mean_isf']
        insulin_needs = isf_nom / mean_isf if mean_isf > 0 else 1.0
        insulin_needs = float(np.clip(insulin_needs, 0.5, 2.0))

        # Map classification to override type and duration
        override_map = {
            'resistance': {
                'type': 'sick',
                'duration_hours': 24.0,
            },
            'sensitivity': {
                'type': 'exercise_recovery',
                'duration_hours': 12.0,
            },
            'carb_change': {
                'type': 'hormone_cycle',
                'duration_hours': 48.0,
            },
        }

        override_info = override_map.get(state, {
            'type': 'custom',
            'duration_hours': 24.0,
        })

        return {
            'type': override_info['type'],
            'insulin_needs_factor': insulin_needs,
            'confidence': confidence,
            'duration_hours': override_info['duration_hours'],
        }


class PatternStateMachine:
    """Track physiological state transitions over time.

    Wraps DriftDetector to maintain state history and detect transitions
    between normal, pre-menstrual, illness, travel, and stress states.

    States: {normal, resistance, sensitivity, carb_change}
    Transitions are logged with timestamps and confidence.
    """

    def __init__(self, detector: DriftDetector, min_confidence: float = 0.3):
        self.detector = detector
        self.min_confidence = min_confidence
        self.current_state = 'stable'
        self.state_history: List[Dict] = []
        self.transitions: List[Dict] = []

    def update(self, timestamp=None):
        """Classify current state and record transitions.

        Args:
            timestamp: optional timestamp for the observation

        Returns:
            dict with current state, whether a transition occurred
        """
        classification = self.detector.classify()
        new_state = classification['state']
        confidence = classification['confidence']

        entry = {
            'state': new_state,
            'confidence': confidence,
            'timestamp': str(timestamp) if timestamp else len(self.state_history),
            'isf_drift_pct': classification['isf_drift_pct'],
            'cr_drift_pct': classification['cr_drift_pct'],
        }
        self.state_history.append(entry)

        transitioned = False
        if new_state != self.current_state and confidence >= self.min_confidence:
            self.transitions.append({
                'from': self.current_state,
                'to': new_state,
                'timestamp': entry['timestamp'],
                'confidence': confidence,
            })
            self.current_state = new_state
            transitioned = True

        return {
            'state': self.current_state,
            'transitioned': transitioned,
            'confidence': confidence,
        }

    def get_state_durations(self) -> Dict[str, int]:
        """Count how many observations were spent in each state."""
        from collections import Counter
        return dict(Counter(e['state'] for e in self.state_history))

    def summary(self) -> Dict:
        """Return summary of state tracking."""
        return {
            'current_state': self.current_state,
            'n_observations': len(self.state_history),
            'n_transitions': len(self.transitions),
            'state_durations': self.get_state_durations(),
            'transitions': self.transitions[-10:],  # last 10
        }


def run_retrospective_tracking(data_path: str, nominal_isf: float = 40.0,
                                nominal_cr: float = 10.0,
                                level: str = 'simple') -> Dict:
    """Run ISF/CR drift tracking over historical patient data.

    Loads Nightscout data, runs physics model to get residuals, then feeds
    residuals into the Kalman tracker to estimate ISF/CR trajectory.

    Args:
        data_path: Path to Nightscout data directory.
        nominal_isf: Baseline ISF from patient profile.
        nominal_cr: Baseline CR from patient profile.
        level: Physics model level ('simple' or 'enhanced').

    Returns:
        dict with: tracker, detector, classification, trajectory, summary
    """
    from .real_data_adapter import build_nightscout_grid
    from .physics_model import (
        physics_predict_window, enhanced_predict_window,
        RESIDUAL_SCALE,
    )

    glucose_scale = NORMALIZATION_SCALES['glucose']
    iob_scale = NORMALIZATION_SCALES['iob']
    cob_scale = NORMALIZATION_SCALES['cob']

    # Load patient data
    grid = build_nightscout_grid(data_path)
    windows_norm = grid['windows']  # (N, T, 8) normalized
    N, T, _F = windows_norm.shape

    tracker = ISFCRTracker(nominal_isf=nominal_isf, nominal_cr=nominal_cr)
    detector = DriftDetector(tracker)

    trajectory = []

    for i in range(N):
        glucose_raw = windows_norm[i, :, 0] * glucose_scale
        iob_raw = windows_norm[i, :, 1] * iob_scale
        cob_raw = windows_norm[i, :, 2] * cob_scale

        if level == 'enhanced':
            time_sin = windows_norm[i, :, 6]
            time_cos = windows_norm[i, :, 7]
            pred = enhanced_predict_window(
                glucose_raw, iob_raw, cob_raw, time_sin, time_cos,
                nominal_isf, nominal_cr)
        else:
            pred = physics_predict_window(
                glucose_raw, iob_raw, cob_raw, nominal_isf, nominal_cr)

        # Accumulate residual and IOB/COB deltas over the window
        residual = float(np.mean(glucose_raw - pred))
        iob_delta = float(iob_raw[-1] - iob_raw[0])
        cob_delta = float(cob_raw[-1] - cob_raw[0])

        state = tracker.update(residual, iob_delta, cob_delta)
        trajectory.append(state)

    classification = detector.classify()
    summary = tracker.drift_summary()

    return {
        'tracker': tracker,
        'detector': detector,
        'classification': classification,
        'trajectory': trajectory,
        'summary': summary,
    }


def main():
    """CLI entry point for retrospective ISF/CR tracking."""
    parser = argparse.ArgumentParser(
        description='Retrospective ISF/CR drift tracking from Nightscout data')
    parser.add_argument('--data-path', required=True,
                        help='Path to Nightscout data directory')
    parser.add_argument('--isf', type=float, default=40.0,
                        help='Nominal ISF (mg/dL per U)')
    parser.add_argument('--cr', type=float, default=10.0,
                        help='Nominal CR (g per U)')
    parser.add_argument('--level', choices=['simple', 'enhanced'],
                        default='simple', help='Physics model level')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    args = parser.parse_args()

    result = run_retrospective_tracking(
        args.data_path, args.isf, args.cr, args.level)

    classification = result['classification']
    summary = result['summary']

    if args.json:
        output = {
            'classification': classification,
            'summary': summary,
            'trajectory_length': len(result['trajectory']),
        }
        override = result['detector'].suggested_override()
        if override:
            output['suggested_override'] = override
        print(json.dumps(output, indent=2))
    else:
        print(f"=== ISF/CR Drift Analysis ===")
        print(f"Windows analyzed: {len(result['trajectory'])}")
        print(f"State: {classification['state']} "
              f"(confidence: {classification['confidence']:.2f})")
        print(f"ISF: {summary['mean_isf']:.1f} mg/dL/U "
              f"(nominal: {result['tracker'].nominal[0]:.1f}, "
              f"drift: {summary['isf_drift_pct']:.1f}%)")
        print(f"CR:  {summary['mean_cr']:.1f} g/U "
              f"(nominal: {result['tracker'].nominal[1]:.1f}, "
              f"drift: {summary['cr_drift_pct']:.1f}%)")
        override = result['detector'].suggested_override()
        if override:
            print(f"\nSuggested override:")
            print(f"  Type: {override['type']}")
            print(f"  Insulin needs: {override['insulin_needs_factor']:.2f}x")
            print(f"  Duration: {override['duration_hours']:.0f}h")
        else:
            print(f"\nNo override needed — parameters stable.")


if __name__ == '__main__':
    main()
