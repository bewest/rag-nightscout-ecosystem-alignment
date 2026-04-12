"""
prediction_validator.py — Prospective validation harness for TIR predictions.

Research basis: EXP-2551 (simulation accuracy validated retrospectively),
               EXP-1717 (combined optimization predicts +2.8% TIR),
               EXP-1901 (temporal stability, within-patient validation).

Validates the digital twin's predictions against outcomes:
  1. **Retrospective holdout**: 80/20 temporal split per patient
  2. **Quasi-prospective**: natural settings drift events as test windows
  3. **Calibration curve**: predicted vs actual TIR delta reliability

The validator answers: "When we predict +3pp TIR from increasing ISF,
does the patient actually see ~3pp improvement?"

Integration: Pipeline Stage 7, after profile_generator (Stage 6b).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .types import (
    MetabolicState, PatientData, PatientProfile,
    OptimalSettings, SettingsOptimizationResult,
)
from .metabolic_engine import compute_metabolic_state, _extract_hours
from .settings_advisor import simulate_tir_with_settings
from .natural_experiment_detector import detect_natural_experiments
from .settings_optimizer import optimize_settings


# ── Thresholds ───────────────────────────────────────────────────────

HOLDOUT_FRACTION = 0.20
TIR_LOW = 70.0
TIR_HIGH = 180.0
MIN_HOLDOUT_SAMPLES = 288  # 1 day minimum


# ── Result Types ─────────────────────────────────────────────────────

@dataclass
class PredictionValidationResult:
    """Result of validating a single patient's TIR predictions."""
    patient_id: str
    n_train: int
    n_test: int
    actual_tir_train: float      # TIR in training period
    actual_tir_test: float       # TIR in test period
    predicted_tir_test: float    # Simulated TIR from digital twin
    tir_delta_actual: float      # actual_test - actual_train
    tir_delta_predicted: float   # predicted_test - actual_train
    prediction_error: float      # |predicted - actual|
    isf_multiplier: float
    cr_multiplier: float
    basal_multiplier: float
    confidence_grade: str = 'unknown'
    n_natural_experiments: int = 0


@dataclass
class ValidationSummary:
    """Aggregate validation across multiple patients."""
    n_patients: int
    mean_absolute_error: float   # MAE of TIR predictions (fraction)
    correlation: float           # r of predicted vs actual delta
    calibration_slope: float     # slope of predicted vs actual (ideal=1.0)
    calibration_intercept: float # intercept (ideal=0.0)
    coverage_80: float           # fraction within ±4pp of prediction
    patients: List[dict] = field(default_factory=list)
    timestamp: str = ''

    @property
    def is_actionable(self) -> bool:
        """Whether predictions are accurate enough for clinical use.

        Criteria:
          - MAE < 3pp (±3 percentage points)
          - Correlation > 0.5 (meaningful directionality)
          - Coverage: >70% of predictions within ±4pp
        """
        return (self.mean_absolute_error < 0.03
                and self.correlation > 0.5
                and self.coverage_80 > 0.70)


# ── Core Validation Logic ────────────────────────────────────────────

def validate_patient(patient: PatientData,
                     patient_id: str = 'unknown',
                     holdout_fraction: float = HOLDOUT_FRACTION,
                     ) -> Optional[PredictionValidationResult]:
    """Validate TIR prediction accuracy on temporal holdout.

    Splits patient data into train/test (80/20 by time), computes
    optimal settings from train period, simulates TIR on test period,
    and compares predicted vs actual TIR.
    """
    N = patient.n_samples
    split_idx = int(N * (1.0 - holdout_fraction))

    if N - split_idx < MIN_HOLDOUT_SAMPLES:
        return None

    # Split data
    def _sl(arr, s, e):
        return arr[s:e].copy() if arr is not None else None

    train = PatientData(
        glucose=patient.glucose[:split_idx].copy(),
        timestamps=patient.timestamps[:split_idx].copy(),
        profile=patient.profile,
        iob=_sl(patient.iob, 0, split_idx),
        cob=_sl(patient.cob, 0, split_idx),
        bolus=_sl(patient.bolus, 0, split_idx),
        carbs=_sl(patient.carbs, 0, split_idx),
        basal_rate=_sl(patient.basal_rate, 0, split_idx),
    )
    test = PatientData(
        glucose=patient.glucose[split_idx:].copy(),
        timestamps=patient.timestamps[split_idx:].copy(),
        profile=patient.profile,
        iob=_sl(patient.iob, split_idx, N),
        cob=_sl(patient.cob, split_idx, N),
        bolus=_sl(patient.bolus, split_idx, N),
        carbs=_sl(patient.carbs, split_idx, N),
        basal_rate=_sl(patient.basal_rate, split_idx, N),
    )

    # Compute metabolic state
    meta_train = compute_metabolic_state(train)
    meta_test = compute_metabolic_state(test)
    hours_train = _extract_hours(train.timestamps)
    hours_test = _extract_hours(test.timestamps)

    # Actual TIR
    def _tir(g):
        valid = g[np.isfinite(g)]
        return float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH))) if len(valid) > 0 else 0.5

    tir_train = _tir(train.glucose)
    tir_test = _tir(test.glucose)

    # Get optimal settings from training period
    isf_mult = cr_mult = basal_mult = 1.0
    confidence = 'unknown'
    n_ne = 0
    try:
        ne_census = detect_natural_experiments(
            train.glucose, meta_train, hours_train, train.profile,
        )
        n_ne = ne_census.total_count
        opt = optimize_settings(ne_census, train.profile)
        isf_mult = opt.optimal.isf_mismatch_ratio
        confidence = opt.optimal.confidence_grade.value
    except Exception:
        isf_mult = 1.0  # no change = null hypothesis

    # Simulate TIR on test period with optimized settings
    _, predicted_tir = simulate_tir_with_settings(
        test.glucose, meta_test, hours_test,
        isf_multiplier=isf_mult,
        cr_multiplier=cr_mult,
        basal_multiplier=basal_mult,
    )

    return PredictionValidationResult(
        patient_id=patient_id,
        n_train=train.n_samples,
        n_test=test.n_samples,
        actual_tir_train=tir_train,
        actual_tir_test=tir_test,
        predicted_tir_test=predicted_tir,
        tir_delta_actual=tir_test - tir_train,
        tir_delta_predicted=predicted_tir - tir_train,
        prediction_error=abs(predicted_tir - tir_test),
        isf_multiplier=isf_mult,
        cr_multiplier=cr_mult,
        basal_multiplier=basal_mult,
        confidence_grade=confidence,
        n_natural_experiments=n_ne,
    )


def validate_batch(patients: Dict[str, PatientData],
                   holdout_fraction: float = HOLDOUT_FRACTION,
                   ) -> ValidationSummary:
    """Validate across a batch of patients.

    Returns aggregate metrics: MAE, correlation, calibration, coverage.
    """
    results: List[PredictionValidationResult] = []
    for pid in sorted(patients.keys()):
        try:
            r = validate_patient(patients[pid], pid, holdout_fraction)
            if r is not None:
                results.append(r)
        except Exception as e:
            print(f"  {pid}: validation failed — {e}")

    if not results:
        return ValidationSummary(
            n_patients=0,
            mean_absolute_error=float('nan'),
            correlation=float('nan'),
            calibration_slope=float('nan'),
            calibration_intercept=float('nan'),
            coverage_80=0.0,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    errors = [r.prediction_error for r in results]
    actual_deltas = [r.tir_delta_actual for r in results]
    pred_deltas = [r.tir_delta_predicted for r in results]

    mae = float(np.mean(errors))

    # Correlation
    if len(results) >= 3:
        corr = float(np.corrcoef(actual_deltas, pred_deltas)[0, 1])
    else:
        corr = float('nan')

    # Calibration: linear fit of predicted vs actual
    if len(results) >= 3:
        try:
            coeffs = np.polyfit(pred_deltas, actual_deltas, 1)
            slope, intercept = float(coeffs[0]), float(coeffs[1])
        except (np.linalg.LinAlgError, ValueError):
            slope, intercept = float('nan'), float('nan')
    else:
        slope, intercept = float('nan'), float('nan')

    # Coverage: fraction within ±4pp
    coverage = float(np.mean([e < 0.04 for e in errors]))

    return ValidationSummary(
        n_patients=len(results),
        mean_absolute_error=mae,
        correlation=corr,
        calibration_slope=slope,
        calibration_intercept=intercept,
        coverage_80=coverage,
        patients=[asdict(r) for r in results],
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


# ── Reporting ────────────────────────────────────────────────────────

def generate_validation_report(summary: ValidationSummary,
                               output_path: Optional[str] = None,
                               ) -> str:
    """Generate a human-readable validation report.

    Returns markdown text. Optionally saves JSON alongside.
    """
    lines = [
        "# TIR Prediction Validation Report",
        "",
        f"**Date**: {summary.timestamp}",
        f"**Patients**: {summary.n_patients}",
        f"**Actionable**: {'✅ Yes' if summary.is_actionable else '❌ No'}",
        "",
        "## Aggregate Metrics",
        "",
        f"| Metric | Value | Target |",
        f"|--------|-------|--------|",
        f"| MAE | {summary.mean_absolute_error*100:.2f}pp | <3pp |",
        f"| Correlation (r) | {summary.correlation:.3f} | >0.5 |",
        f"| Calibration slope | {summary.calibration_slope:.3f} | ~1.0 |",
        f"| Coverage (±4pp) | {summary.coverage_80*100:.0f}% | >70% |",
        "",
    ]

    if summary.patients:
        lines.extend([
            "## Per-Patient Results",
            "",
            "| Patient | Train TIR | Test TIR | Predicted | Error | NE Windows |",
            "|---------|-----------|----------|-----------|-------|------------|",
        ])
        for p in summary.patients:
            lines.append(
                f"| {p['patient_id']} "
                f"| {p['actual_tir_train']*100:.1f}% "
                f"| {p['actual_tir_test']*100:.1f}% "
                f"| {p['predicted_tir_test']*100:.1f}% "
                f"| {p['prediction_error']*100:.1f}pp "
                f"| {p['n_natural_experiments']} |"
            )
        lines.append("")

    report = "\n".join(lines)

    if output_path:
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report)
        # Also save JSON
        json_path = output_path.replace('.md', '.json')
        with open(json_path, 'w') as f:
            json.dump(asdict(summary), f, indent=2, default=str)

    return report
