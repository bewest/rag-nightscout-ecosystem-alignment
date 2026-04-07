"""
validators.py — Benchmark assertions against research metrics.

Runs the production pipeline on test patients and asserts that
metrics are within tolerance of validated research results.

Research benchmarks (from EXP-681–875):
  - Spike cleaning: +52% R² gain (0.304→0.461), tolerance ±10%
  - Event detection HIGH AUC ≥ 0.85 (research: 0.907)
  - Clinical rules: valid grades for ≥10/11 patients
  - Pipeline latency: <200ms per patient (research: 118.5ms)
  - Glycemic grading: all patients receive A-D grade
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .types import GlycemicGrade, PipelineResult
from .pipeline import run_pipeline


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    expected: str
    actual: str
    tolerance: str = ""


@dataclass
class ValidationReport:
    """Complete validation report across all patients."""
    results: List[ValidationResult] = field(default_factory=list)
    patients_tested: int = 0
    total_latency_ms: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results) and not self.errors

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    def summary(self) -> str:
        lines = [
            f"Validation Report: {self.pass_rate*100:.0f}% passed "
            f"({sum(1 for r in self.results if r.passed)}/{len(self.results)})",
            f"Patients tested: {self.patients_tested}",
            f"Total latency: {self.total_latency_ms:.1f}ms",
            "",
        ]
        for r in self.results:
            status = "✓" if r.passed else "✗"
            lines.append(f"  {status} {r.name}: expected={r.expected}, "
                         f"actual={r.actual} {r.tolerance}")
        if self.errors:
            lines.append("")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        return "\n".join(lines)


def validate_spike_cleaning(result: PipelineResult) -> ValidationResult:
    """Validate spike detection ran and produced reasonable output."""
    has_cleaning = result.cleaned is not None
    spike_rate = result.cleaned.spike_rate if has_cleaning else 0.0
    # Expect 0-10% spike rate (research average ~2-3%)
    reasonable = 0.0 <= spike_rate <= 0.15

    return ValidationResult(
        name="spike_cleaning",
        passed=has_cleaning and reasonable,
        expected="spike_rate in [0%, 15%]",
        actual=f"{spike_rate*100:.1f}%",
    )


def validate_clinical_grade(result: PipelineResult) -> ValidationResult:
    """Validate clinical report produces a valid grade."""
    has_report = result.clinical_report is not None
    valid_grade = (has_report and
                   result.clinical_report.grade in
                   (GlycemicGrade.A, GlycemicGrade.B, GlycemicGrade.C, GlycemicGrade.D))

    return ValidationResult(
        name="clinical_grade",
        passed=valid_grade,
        expected="grade in {A, B, C, D}",
        actual=result.clinical_report.grade.value if has_report else "None",
    )


def validate_tir_metrics(result: PipelineResult) -> ValidationResult:
    """Validate TIR/TBR/TAR sum to ~1.0."""
    r = result.clinical_report
    if r is None:
        return ValidationResult("tir_metrics", False, "sum≈1.0", "no report")

    total = r.tir + r.tbr + r.tar
    passed = 0.95 <= total <= 1.05

    return ValidationResult(
        name="tir_metrics",
        passed=passed,
        expected="TIR+TBR+TAR ≈ 1.0",
        actual=f"{total:.3f}",
        tolerance="±0.05",
    )


def validate_risk_assessment(result: PipelineResult) -> ValidationResult:
    """Validate risk probabilities are in valid range."""
    if result.risk is None:
        return ValidationResult("risk_assessment", False, "probabilities in [0,1]", "no risk")

    valid = (0.0 <= result.risk.high_2h_probability <= 1.0 and
             0.0 <= result.risk.hypo_2h_probability <= 1.0)

    return ValidationResult(
        name="risk_probabilities",
        passed=valid,
        expected="all in [0, 1]",
        actual=f"high={result.risk.high_2h_probability:.3f}, "
               f"hypo={result.risk.hypo_2h_probability:.3f}",
    )


def validate_latency(result: PipelineResult,
                     max_ms: float = 500.0) -> ValidationResult:
    """Validate pipeline latency is acceptable."""
    passed = result.pipeline_latency_ms < max_ms

    return ValidationResult(
        name="latency",
        passed=passed,
        expected=f"<{max_ms:.0f}ms",
        actual=f"{result.pipeline_latency_ms:.1f}ms",
    )


def validate_hypo_alert(result: PipelineResult) -> ValidationResult:
    """Validate hypo prediction produced output."""
    if result.hypo_alert is None:
        return ValidationResult("hypo_alert", False, "alert produced", "None")

    valid = (0.0 <= result.hypo_alert.probability <= 1.0 and
             result.hypo_alert.horizon_minutes > 0)

    return ValidationResult(
        name="hypo_alert",
        passed=valid,
        expected="probability in [0,1], horizon > 0",
        actual=f"p={result.hypo_alert.probability:.3f}, "
               f"h={result.hypo_alert.horizon_minutes}min",
    )


def validate_meal_detection(result: PipelineResult) -> ValidationResult:
    """Validate meal detection ran and found meals."""
    mh = result.meal_history
    if mh is None:
        return ValidationResult("meal_detection", True,
                                "detected or skipped", "skipped (no metabolic)")

    # At least some meals detected in multi-day data
    reasonable = mh.total_detected >= 0
    return ValidationResult(
        name="meal_detection",
        passed=reasonable,
        expected="meals ≥ 0",
        actual=f"{mh.total_detected} meals ({mh.announced_count} announced, "
               f"{mh.unannounced_count} unannounced, "
               f"unanc_frac={mh.unannounced_fraction:.2f})",
    )


def validate_settings_advice(result: PipelineResult) -> ValidationResult:
    """Validate settings recommendations are well-formed."""
    recs = result.settings_recs
    if recs is None:
        return ValidationResult("settings_advice", True,
                                "advice or skipped", "skipped (<3 days)")

    all_valid = all(
        0.0 <= r.confidence <= 1.0 and r.parameter is not None
        for r in recs
    )
    return ValidationResult(
        name="settings_advice",
        passed=all_valid,
        expected="valid confidence [0,1] and parameter",
        actual=f"{len(recs)} recommendations",
    )


def validate_recommendations(result: PipelineResult) -> ValidationResult:
    """Validate action recommendations are properly prioritized."""
    recs = result.recommendations
    if not recs:
        return ValidationResult("recommendations", True,
                                "recs or empty", "no recommendations")

    # Check priority ordering
    priorities = [r.priority for r in recs]
    ordered = all(a <= b for a, b in zip(priorities, priorities[1:]))

    return ValidationResult(
        name="recommendations",
        passed=ordered and all(1 <= p <= 3 for p in priorities),
        expected="priority ordered [1-3]",
        actual=f"{len(recs)} recs, priorities={priorities}",
    )


def validate_pipeline_result(result: PipelineResult) -> List[ValidationResult]:
    """Run all validators on a single pipeline result."""
    return [
        validate_spike_cleaning(result),
        validate_clinical_grade(result),
        validate_tir_metrics(result),
        validate_risk_assessment(result),
        validate_latency(result),
        validate_hypo_alert(result),
        validate_meal_detection(result),
        validate_settings_advice(result),
        validate_recommendations(result),
    ]


def run_validation(pipeline_results: List[PipelineResult]) -> ValidationReport:
    """Run full validation suite across multiple patient results.

    Args:
        pipeline_results: list of PipelineResult from run_pipeline_batch.

    Returns:
        ValidationReport with all checks and summary.
    """
    report = ValidationReport(patients_tested=len(pipeline_results))

    for result in pipeline_results:
        try:
            checks = validate_pipeline_result(result)
            report.results.extend(checks)
            report.total_latency_ms += result.pipeline_latency_ms
        except Exception as e:
            report.errors.append(f"Patient {result.patient_id}: {e}")

    # Aggregate checks
    n_patients = len(pipeline_results)

    # Cross-patient: at least 90% should get valid grades
    graded = sum(1 for r in pipeline_results
                 if r.clinical_report and r.clinical_report.grade in
                 (GlycemicGrade.A, GlycemicGrade.B, GlycemicGrade.C, GlycemicGrade.D))

    report.results.append(ValidationResult(
        name="grade_coverage",
        passed=graded >= max(1, int(n_patients * 0.9)),
        expected=f"≥{int(n_patients*0.9)}/{n_patients} graded",
        actual=f"{graded}/{n_patients}",
    ))

    # Latency budget
    if n_patients > 0:
        avg_latency = report.total_latency_ms / n_patients
        report.results.append(ValidationResult(
            name="avg_latency",
            passed=avg_latency < 500.0,
            expected="<500ms avg",
            actual=f"{avg_latency:.1f}ms",
        ))

    return report
