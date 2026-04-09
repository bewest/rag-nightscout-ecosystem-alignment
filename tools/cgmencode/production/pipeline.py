"""
pipeline.py — Orchestrator chaining all production inference modules.

Chains: ingest → clean → flux → [detect, predict, assess, analyze, meals, advise] → recommend

Target latency: <500ms per patient (with all new modules).

The pipeline handles missing data gracefully:
- No insulin data? Skip metabolic engine, use BG-only risk assessment
- No carbs? Skip CR scoring, use neutral score
- < 1 week data? Skip pattern analysis and meal prediction
- New patient? Use population defaults via onboarding
"""

from __future__ import annotations

import time
from typing import List, Optional

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
from .meal_detector import detect_meal_events, build_meal_history, classify_all_meal_responses, classify_meal_archetypes
from .meal_predictor import build_timing_models, predict_next_meal, MealMLModel
from .settings_advisor import generate_settings_advice, analyze_periods, advise_isf_segmented
from .recommender import generate_recommendations
from .clinical_rules import (
    generate_clinical_report, compute_correction_energy,
    assess_correction_timing, assess_aid_compensation,
    compute_fidelity_grade,
)
from .natural_experiment_detector import detect_natural_experiments


def run_pipeline(patient: PatientData,
                 personal_params: Optional[dict] = None,
                 skip_patterns: bool = False,
                 current_hour: Optional[float] = None,
                 forecast_config: Optional[dict] = None,
                 ) -> PipelineResult:
    """Run complete inference pipeline on a single patient.

    This is the primary public API. Chains all modules with
    graceful degradation on missing data.

    Args:
        patient: PatientData with at minimum glucose + timestamps + profile.
        personal_params: optional calibrated personal parameters.
        skip_patterns: skip pattern analysis (faster, for real-time use).
        current_hour: fractional hour for meal prediction (default: last timestamp).
        forecast_config: optional dict to enable glucose forecasting.
            Keys: patient_id (str), window (str, default 'w48'),
            models_dir (str), device (str, default 'cpu'),
            isf (float, optional).

    Returns:
        PipelineResult with all available inference outputs.
    """
    start = time.perf_counter()
    warnings: List[str] = []

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

    # ── Stage 4c′: Fidelity Assessment (EXP-1531–1538) ───────────
    if metabolic is not None:
        try:
            fidelity = compute_fidelity_grade(
                metabolic=metabolic,
                glucose=cleaned.glucose,
                hours=hours,
                days_of_data=patient.days_of_data,
                ada_grade=clinical_report.grade,
            )
            clinical_report.fidelity = fidelity
        except Exception as e:
            warnings.append(f"Fidelity assessment failed: {e}")

    # ── Stage 4d: Pattern Analysis ────────────────────────────────
    patterns = None
    if not skip_patterns and patient.days_of_data >= 7.0:
        try:
            patterns = analyze_patterns(cleaned.glucose, metabolic, hours)
        except Exception as e:
            warnings.append(f"Pattern analysis failed: {e}")
    elif not skip_patterns:
        warnings.append(f"Only {patient.days_of_data:.1f} days — patterns need ≥7 days")

    # ── Stage 4e: Glucose Forecast (transformer ensemble) ─────────
    forecast = None
    if forecast_config and metabolic is not None:
        try:
            from .glucose_forecast import predict_trajectory
            fc = forecast_config
            forecast = predict_trajectory(
                patient=patient,
                metabolic=metabolic,
                hours=hours,
                glucose=cleaned.glucose,
                patient_id=fc.get('patient_id', patient.patient_id),
                window=fc.get('window', 'w48'),
                models_dir=fc.get('models_dir'),
                device=fc.get('device', 'cpu'),
                isf=fc.get('isf'),
            )
            if forecast is None:
                warnings.append("Forecast models not found — skipped")
        except ImportError:
            warnings.append("PyTorch not available — forecast skipped")
        except Exception as e:
            warnings.append(f"Glucose forecast failed: {e}")

    # ── Stage 5: Meal Detection ───────────────────────────────────
    meal_history = None
    meal_prediction = None
    meal_responses = None
    if metabolic is not None:
        try:
            meals = detect_meal_events(
                cleaned.glucose, metabolic, hours,
                patient.timestamps, patient.profile)

            # Meal archetype clustering (EXP-1591–1598)
            classify_meal_archetypes(cleaned.glucose, meals)

            meal_history = build_meal_history(meals, patient.days_of_data)

            # Meal response phenotyping (EXP-514)
            meal_responses = classify_all_meal_responses(
                cleaned.glucose, meals, metabolic)

            # Meal timing prediction (needs ≥7 days of meal history)
            if patient.days_of_data >= 7.0 and meal_history.total_detected >= 10:
                timing_models = build_timing_models(meal_history, patient.days_of_data)

                # Train ML model if enough data (EXP-1129: dual-mode AUC=0.846/0.942)
                ml_model = None
                if patient.days_of_data >= 14.0 and meal_history.total_detected >= 20:
                    ml_model = MealMLModel()
                    net_flux = metabolic.net_flux if hasattr(metabolic, 'net_flux') else None
                    supply = metabolic.supply if hasattr(metabolic, 'supply') else None
                    if not ml_model.train(meal_history, cleaned.glucose,
                                          net_flux=net_flux,
                                          supply=supply,
                                          days_of_data=patient.days_of_data):
                        ml_model = None

                if timing_models:
                    c_hour = current_hour if current_hour is not None else float(hours[-1])

                    # Gather ML context for prediction
                    ml_kwargs = {}
                    if ml_model is not None:
                        N = len(cleaned.glucose)
                        last_meal_idx = max(m.index for m in meal_history.meals)

                        # 60-min glucose window (13 steps) for pre-meal features
                        win_start = max(0, N - 13)
                        glucose_window = cleaned.glucose[win_start:N]

                        # Supply window for IOB proxy
                        supply_arr = supply if supply is not None else np.zeros(N)
                        supply_window = supply_arr[win_start:N]

                        # Fasting duration estimate
                        mean_g = float(np.nanmean(cleaned.glucose[max(0, N - 288):N]))
                        fasting_steps = 0
                        for j in range(N - 1, max(0, N - 288), -1):
                            if not np.isnan(cleaned.glucose[j]) and cleaned.glucose[j] > mean_g + 15:
                                break
                            fasting_steps += 1

                        ml_kwargs = dict(
                            ml_model=ml_model,
                            glucose_current=float(cleaned.glucose[-1]),
                            glucose_15min_ago=float(cleaned.glucose[-4]) if N > 3 else float(cleaned.glucose[-1]),
                            glucose_30min_ago=float(cleaned.glucose[-7]) if N > 6 else float(cleaned.glucose[-1]),
                            minutes_since_last_meal=float((N - 1 - last_meal_idx) * 5),
                            meals_today_count=int(sum(1 for m in meal_history.meals
                                                      if m.index >= N - 288)),
                            net_flux_current=float(net_flux[-1]) if net_flux is not None and len(net_flux) > 0 else 0.0,
                            day_index=N // 288,
                            glucose_window=glucose_window,
                            supply_window=supply_window,
                            fasting_hours=fasting_steps * 5.0 / 60.0,
                            current_step=N - 1,
                        )

                    meal_prediction = predict_next_meal(
                        timing_models, c_hour, meal_history, **ml_kwargs)
        except Exception as e:
            warnings.append(f"Meal detection failed: {e}")

    # ── Stage 5b: Advanced Analytics ──────────────────────────────
    period_metrics = None
    correction_energy = None
    bolus_safety = None
    aid_compensation = None

    # Period-by-period analysis
    if metabolic is not None and patient.days_of_data >= 3.0:
        try:
            period_metrics = analyze_periods(
                cleaned.glucose, metabolic, hours,
                clinical_report, patient.profile, patient.days_of_data)
        except Exception as e:
            warnings.append(f"Period analysis failed: {e}")

    # Correction energy scoring (EXP-559)
    if metabolic is not None:
        try:
            correction_energy = compute_correction_energy(
                metabolic, hours, cleaned.glucose, patient.days_of_data)
        except Exception as e:
            warnings.append(f"Correction energy failed: {e}")

    # Correction timing safety
    try:
        bolus_safety = assess_correction_timing(
            patient.bolus, cleaned.glucose, patient.timestamps)
    except Exception as e:
        warnings.append(f"Bolus safety failed: {e}")

    # AID compensation detection (EXP-747)
    try:
        aid_compensation = assess_aid_compensation(clinical_report, metabolic)
    except Exception as e:
        warnings.append(f"AID compensation failed: {e}")

    # ── Stage 5c: Natural Experiment Detection (EXP-1551) ─────────
    natural_experiments = None
    if patient.days_of_data >= 1.0:
        try:
            natural_experiments = detect_natural_experiments(
                patient=patient,
                metabolic=metabolic,
            )
        except Exception as e:
            warnings.append(f"Natural experiment detection failed: {e}")

    # ── Stage 6: Settings Advisor ─────────────────────────────────
    settings_recs = None
    if patient.days_of_data >= 3.0:
        try:
            settings_recs = generate_settings_advice(
                cleaned.glucose, metabolic, hours,
                clinical_report, patient.profile, patient.days_of_data)

            # ISF segmentation recommendations (EXP-765)
            isf_segment_recs = advise_isf_segmented(
                cleaned.glucose, metabolic, hours,
                clinical_report, patient.profile, patterns, patient.days_of_data)
            if isf_segment_recs:
                if settings_recs is None:
                    settings_recs = []
                settings_recs.extend(isf_segment_recs)
                settings_recs.sort(key=lambda r: abs(r.predicted_tir_delta), reverse=True)
        except Exception as e:
            warnings.append(f"Settings advisor failed: {e}")

    # ── Stage 7: Action Recommendations ───────────────────────────
    recommendations = generate_recommendations(
        clinical=clinical_report,
        hypo_alert=hypo_alert,
        meal_prediction=meal_prediction,
        settings_recs=settings_recs,
        meal_history=meal_history,
    )

    # ── Assemble result ───────────────────────────────────────────
    elapsed = (time.perf_counter() - start) * 1000.0

    return PipelineResult(
        patient_id=patient.patient_id,
        cleaned=cleaned,
        metabolic=metabolic,
        risk=risk,
        hypo_alert=hypo_alert,
        clinical_report=clinical_report,
        patterns=patterns,
        onboarding=onboarding,
        meal_history=meal_history,
        meal_prediction=meal_prediction,
        settings_recs=settings_recs,
        recommendations=recommendations,
        period_metrics=period_metrics,
        correction_energy=correction_energy,
        meal_responses=meal_responses,
        bolus_safety=bolus_safety,
        aid_compensation=aid_compensation,
        forecast=forecast,
        natural_experiments=natural_experiments,
        pipeline_latency_ms=elapsed,
        warnings=warnings,
    )


def run_pipeline_batch(patients: list[PatientData],
                       **kwargs) -> list[PipelineResult]:
    """Run pipeline on multiple patients sequentially."""
    return [run_pipeline(p, **kwargs) for p in patients]
