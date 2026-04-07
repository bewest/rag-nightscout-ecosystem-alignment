"""
pipeline.py — Orchestrator chaining all production inference modules.

Chains: ingest → clean → flux → [detect, predict, assess, analyze] → report

Target latency: <200ms per patient (research baseline: 118.5ms).

The pipeline handles missing data gracefully:
- No insulin data? Skip metabolic engine, use BG-only risk assessment
- No carbs? Skip CR scoring, use neutral score
- < 2 weeks data? Skip pattern analysis
- New patient? Use population defaults via onboarding
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from .types import (
    PatientData, PipelineResult, OnboardingState,
)
from .data_quality import clean_glucose
from .metabolic_engine import compute_metabolic_state, _extract_hours
from .event_detector import classify_risk_simple
from .hypo_predictor import predict_hypo, calibrate_threshold
from .clinical_rules import generate_clinical_report
from .pattern_analyzer import analyze_patterns
from .patient_onboarding import get_onboarding_state


def run_pipeline(patient: PatientData,
                 personal_params: Optional[dict] = None,
                 skip_patterns: bool = False,
                 ) -> PipelineResult:
    """Run complete inference pipeline on a single patient.

    This is the primary public API. Chains all modules with
    graceful degradation on missing data.

    Args:
        patient: PatientData with at minimum glucose + timestamps + profile.
        personal_params: optional calibrated personal parameters.
        skip_patterns: skip pattern analysis (faster, for real-time use).

    Returns:
        PipelineResult with all available inference outputs.
    """
    start = time.perf_counter()
    warnings = []

    # ── Stage 1: Data Quality (spike cleaning) ────────────────────
    cleaned = clean_glucose(patient.glucose)
    if cleaned.n_spikes > 0:
        pct = cleaned.spike_rate * 100
        warnings.append(f"Cleaned {cleaned.n_spikes} spikes ({pct:.1f}% of readings)")

    # ── Stage 2: Onboarding (determine what models to use) ────────
    onboarding = get_onboarding_state(
        patient.days_of_data,
        personal_params=personal_params,
    )

    # ── Stage 3: Metabolic Engine (physics layer) ─────────────────
    metabolic = None
    if patient.has_insulin_data:
        try:
            metabolic = compute_metabolic_state(patient)
        except Exception as e:
            warnings.append(f"Metabolic engine failed: {e}")
    else:
        warnings.append("No insulin data — metabolic analysis skipped")

    # ── Stage 4a: Event Detection / Risk Classification ───────────
    risk = None
    try:
        risk = classify_risk_simple(cleaned.glucose, metabolic)
    except Exception as e:
        warnings.append(f"Event detection failed: {e}")

    # ── Stage 4b: Hypo Prediction ─────────────────────────────────
    hypo_alert = None
    try:
        # Personalized threshold if enough data
        threshold = None
        if patient.days_of_data >= 3.0:
            threshold = calibrate_threshold(patient.glucose)

        hypo_alert = predict_hypo(
            cleaned.glucose,
            metabolic=metabolic,
            personal_threshold=threshold,
        )
    except Exception as e:
        warnings.append(f"Hypo prediction failed: {e}")

    # ── Stage 4c: Clinical Report ─────────────────────────────────
    hours = _extract_hours(patient.timestamps)
    clinical_report = generate_clinical_report(
        glucose=cleaned.glucose,
        metabolic=metabolic,
        profile=patient.profile,
        carbs=patient.carbs,
        bolus=patient.bolus,
        hours=hours,
    )

    # ── Stage 4d: Pattern Analysis (requires ≥2 weeks) ───────────
    patterns = None
    if not skip_patterns and patient.days_of_data >= 7.0:
        try:
            patterns = analyze_patterns(cleaned.glucose, metabolic, hours)
        except Exception as e:
            warnings.append(f"Pattern analysis failed: {e}")
    elif not skip_patterns:
        warnings.append(f"Only {patient.days_of_data:.1f} days of data — patterns need ≥7 days")

    # ── Assemble result ───────────────────────────────────────────
    elapsed = (time.perf_counter() - start) * 1000.0  # ms

    return PipelineResult(
        patient_id=patient.patient_id,
        cleaned=cleaned,
        metabolic=metabolic,
        risk=risk,
        hypo_alert=hypo_alert,
        clinical_report=clinical_report,
        patterns=patterns,
        onboarding=onboarding,
        pipeline_latency_ms=elapsed,
        warnings=warnings,
    )


def run_pipeline_batch(patients: list[PatientData],
                       **kwargs) -> list[PipelineResult]:
    """Run pipeline on multiple patients sequentially.

    Args:
        patients: list of PatientData.
        **kwargs: passed to run_pipeline.

    Returns:
        List of PipelineResults, one per patient.
    """
    return [run_pipeline(p, **kwargs) for p in patients]
