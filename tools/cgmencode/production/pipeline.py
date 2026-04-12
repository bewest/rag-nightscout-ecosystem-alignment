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

import logging
import time
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

from .types import (
    PatientData, PipelineResult, OnboardingState,
    ControllerType,
)
from .data_quality import clean_glucose
from .metabolic_engine import compute_metabolic_state, _extract_hours, estimate_dia_discrepancy, decompose_two_component_dia
from .event_detector import classify_risk_simple
from .hypo_predictor import predict_hypo, calibrate_threshold
from .clinical_rules import generate_clinical_report
from .pattern_analyzer import analyze_patterns
from .patient_onboarding import get_onboarding_state
from .meal_detector import detect_meal_events, build_meal_history, classify_all_meal_responses, classify_meal_archetypes
from .meal_predictor import build_timing_models, predict_next_meal, MealMLModel
from .settings_advisor import generate_settings_advice, analyze_periods, advise_isf_segmented, advise_circadian_isf, advise_context_cr, assess_overnight_drift, compute_loop_workload
from .recommender import generate_recommendations, detect_controller_type, get_controller_behavior, adjust_confidence_for_controller
from .hypo_risk import compute_hypo_risk
from .loop_quality import assess_loop_quality
from .clinical_rules import (
    generate_clinical_report, compute_correction_energy,
    assess_correction_timing, assess_aid_compensation,
    compute_fidelity_grade,
)
from .natural_experiment_detector import detect_natural_experiments
from .settings_optimizer import optimize_settings


def _extract_correction_events(
    glucose: np.ndarray,
    bolus: Optional[np.ndarray],
    carbs: Optional[np.ndarray],
    hours: np.ndarray,
    profile: 'PatientProfile',
) -> List[dict]:
    """Extract correction bolus events for settings advisories.

    A correction event is a bolus >0.1U when glucose is above target and
    no significant carbs appear within ±1 hour (12 steps at 5-min cadence).
    """
    if bolus is None or len(glucose) < 49:
        return []

    N = len(glucose)
    target_high = getattr(profile, 'target_high', 180.0)
    events: List[dict] = []

    for i in range(N):
        if np.isnan(bolus[i]) or bolus[i] <= 0.1:
            continue

        # Skip if glucose at bolus time is missing or below target
        if np.isnan(glucose[i]) or glucose[i] <= target_high:
            continue

        # Skip if significant carbs within ±12 steps (1 hour)
        carb_window_lo = max(0, i - 12)
        carb_window_hi = min(N, i + 13)
        if carbs is not None:
            carb_sum = float(np.nansum(carbs[carb_window_lo:carb_window_hi]))
            if carb_sum > 5.0:
                continue

        # Need 48 steps (4h) of future glucose
        end_idx = i + 48
        if end_idx >= N:
            continue

        start_bg = float(glucose[i])
        end_bg = float(glucose[end_idx])
        if np.isnan(end_bg):
            continue

        window = glucose[i:end_idx + 1]
        valid_mask = ~np.isnan(window)
        if valid_mask.sum() < 6:
            continue

        drop = start_bg - end_bg

        # Check if glucose went below 70 in the window
        went_below_70 = bool(np.nanmin(window) < 70.0)

        # Rebound detection: find nadir, check if BG rose >30 above nadir after it
        nadir_val = float(np.nanmin(window))
        nadir_pos = int(np.nanargmin(np.where(valid_mask, window, np.inf)))
        rebound = False
        rebound_magnitude = 0.0
        if nadir_pos < len(window) - 1:
            post_nadir = window[nadir_pos + 1:]
            post_valid = post_nadir[~np.isnan(post_nadir)]
            if len(post_valid) > 0:
                peak_after_nadir = float(np.max(post_valid))
                rebound_magnitude = peak_after_nadir - nadir_val
                rebound = rebound_magnitude > 30.0

        # TIR change: fraction of readings 70-180 in 48 steps pre vs post
        pre_start = max(0, i - 48)
        pre_window = glucose[pre_start:i]
        post_window = glucose[i:end_idx + 1]

        def _tir_frac(arr: np.ndarray) -> float:
            v = arr[~np.isnan(arr)]
            if len(v) == 0:
                return 0.0
            return float(np.mean((v >= 70.0) & (v <= 180.0)))

        tir_change = _tir_frac(post_window) - _tir_frac(pre_window)

        hour = float(hours[i]) if i < len(hours) else 0.0

        events.append({
            'start_bg': start_bg,
            'drop_4h': drop,
            'dose': float(bolus[i]),
            'hour': hour,
            'tir_change': tir_change,
            'rebound': rebound,
            'rebound_magnitude': rebound_magnitude,
            'went_below_70': went_below_70,
        })

    return events


def _extract_meal_events(
    glucose: np.ndarray,
    bolus: Optional[np.ndarray],
    carbs: Optional[np.ndarray],
    hours: np.ndarray,
) -> List[dict]:
    """Extract meal events for CR adequacy advisories.

    A meal event is a carb entry >5g with any bolus within ±2 steps (10 min).
    """
    if carbs is None or len(glucose) < 49:
        return []

    N = len(glucose)
    events: List[dict] = []

    for i in range(N):
        if np.isnan(carbs[i]) or carbs[i] <= 5.0:
            continue

        # Sum bolus within ±2 steps
        b_lo = max(0, i - 2)
        b_hi = min(N, i + 3)
        if bolus is not None:
            bolus_sum = float(np.nansum(bolus[b_lo:b_hi]))
        else:
            bolus_sum = 0.0

        pre_meal_bg = float(glucose[i]) if not np.isnan(glucose[i]) else np.nan
        if np.isnan(pre_meal_bg):
            continue

        # 4-hour post-meal glucose
        post_idx = i + 48
        if post_idx >= N:
            continue
        post_meal_bg = float(glucose[post_idx])
        if np.isnan(post_meal_bg):
            continue

        hour = float(hours[i]) if i < len(hours) else 0.0

        events.append({
            'carbs': float(carbs[i]),
            'bolus': bolus_sum,
            'pre_meal_bg': pre_meal_bg,
            'post_meal_bg_4h': post_meal_bg,
            'hour': hour,
        })

    return events


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

    # ── Stage 6a: Settings Optimization from NE (EXP-1701) ──────
    optimal_settings = None
    if natural_experiments is not None and patient.days_of_data >= 3.0:
        try:
            optimal_settings = optimize_settings(
                census=natural_experiments,
                profile=patient.profile,
            )
        except Exception as e:
            warnings.append(f"Settings optimization failed: {e}")

    # ── Stage 6: Settings Advisor ─────────────────────────────────
    settings_recs = None
    controller_type = detect_controller_type(patient)
    controller_behavior = get_controller_behavior(controller_type)
    overnight_assessment = None
    loop_workload = None

    # Extract correction and meal events for settings advisories
    correction_events = None
    meal_events = None
    try:
        correction_events = _extract_correction_events(
            cleaned.glucose, patient.bolus, patient.carbs,
            hours, patient.profile) or None
    except Exception as e:
        warnings.append(f"Correction event extraction failed: {e}")
    try:
        meal_events = _extract_meal_events(
            cleaned.glucose, patient.bolus, patient.carbs, hours) or None
    except Exception as e:
        warnings.append(f"Meal event extraction failed: {e}")

    if patient.days_of_data >= 3.0:
        try:
            settings_recs = generate_settings_advice(
                cleaned.glucose, metabolic, hours,
                clinical_report, patient.profile, patient.days_of_data,
                carbs=patient.carbs, iob=patient.iob,
                cob=patient.cob, actual_basal=patient.basal_rate,
                bolus=patient.bolus,
                correction_events=correction_events,
                meal_events=meal_events)

            # ISF segmentation recommendations (EXP-765)
            isf_segment_recs = advise_isf_segmented(
                cleaned.glucose, metabolic, hours,
                clinical_report, patient.profile, patterns, patient.days_of_data)
            if isf_segment_recs:
                if settings_recs is None:
                    settings_recs = []
                settings_recs.extend(isf_segment_recs)
                settings_recs.sort(key=lambda r: abs(r.predicted_tir_delta), reverse=True)

            # Adjust confidence based on controller behavior (EXP-2081)
            if settings_recs:
                settings_recs = adjust_confidence_for_controller(
                    settings_recs, controller_type)
        except Exception as e:
            warnings.append(f"Settings advisor failed: {e}")

        # Overnight drift assessment (EXP-2371–2378)
        try:
            overnight_assessment = assess_overnight_drift(
                cleaned.glucose, hours, patient.profile, patient.days_of_data,
                iob=patient.iob, cob=patient.cob,
                actual_basal=patient.basal_rate)
        except Exception as e:
            warnings.append(f"Overnight drift assessment failed: {e}")

        # Loop workload report (EXP-2391–2396)
        if patient.basal_rate is not None:
            try:
                loop_workload = compute_loop_workload(
                    hours, patient.basal_rate, patient.profile)
            except Exception as e:
                warnings.append(f"Loop workload analysis failed: {e}")

    if controller_type != ControllerType.UNKNOWN:
        warnings.append(
            f"Controller detected: {controller_type.value} "
            f"({controller_behavior.compensation_style}). "
            f"Settings visibility: {controller_behavior.settings_visibility:.0%}."
        )

    # ── Stage 7: Action Recommendations ───────────────────────────
    recommendations = generate_recommendations(
        clinical=clinical_report,
        hypo_alert=hypo_alert,
        meal_prediction=meal_prediction,
        settings_recs=settings_recs,
        meal_history=meal_history,
    )

    # ── Stage 8: DIA Discrepancy Analysis (EXP-2351–2358) ─────────
    dia_discrepancy = None
    two_component_dia = None
    if metabolic is not None and patient.has_insulin_data:
        try:
            dia_discrepancy = estimate_dia_discrepancy(patient, metabolic)
            if dia_discrepancy.discrepancy_ratio and dia_discrepancy.discrepancy_ratio > 2.0:
                warnings.append(
                    f"DIA discrepancy: glucose response DIA "
                    f"({dia_discrepancy.glucose_dia_hours:.1f}h) is "
                    f"{dia_discrepancy.discrepancy_ratio:.1f}× longer than "
                    f"IOB decay DIA ({dia_discrepancy.iob_dia_hours:.1f}h)."
                )
        except Exception as e:
            warnings.append(f"DIA discrepancy analysis failed: {e}")

        # Two-component DIA decomposition (EXP-2525)
        try:
            two_component_dia = decompose_two_component_dia(patient, metabolic)
        except Exception as e:
            warnings.append(f"Two-component DIA decomposition failed: {e}")

    # ── Stage 9: Hypo Early Warning (EXP-2539) ────────────────────
    hypo_risk_result = None
    if len(cleaned.glucose) >= 3:
        try:
            recent = cleaned.glucose[-12:].tolist()
            recent_clean = [v for v in recent if not np.isnan(v)]
            if len(recent_clean) >= 3:
                hypo_risk_result = compute_hypo_risk(recent_clean)
        except Exception as e:
            warnings.append(f"Hypo risk assessment failed: {e}")

    # ── Stage 10: Loop Quality Assessment (EXP-2538/2540) ─────────
    loop_quality_result = None
    if patient.days_of_data >= 3.0 and patient.basal_rate is not None:
        try:
            # Get scheduled basal from profile
            basal_vals = [e.get('value', e.get('rate', 0.8))
                          for e in patient.profile.basal_schedule]
            sched_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

            loop_quality_result = assess_loop_quality(
                glucose=cleaned.glucose,
                hours=hours,
                basal_rate=patient.basal_rate,
                bolus=patient.bolus,
                iob=patient.iob,
                scheduled_basal=sched_basal,
                days_of_data=patient.days_of_data,
            )
        except Exception as e:
            warnings.append(f"Loop quality assessment failed: {e}")

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
        optimal_settings=optimal_settings,
        dia_discrepancy=dia_discrepancy,
        two_component_dia=two_component_dia,
        overnight_assessment=overnight_assessment,
        loop_workload=loop_workload,
        hypo_risk=hypo_risk_result,
        loop_quality=loop_quality_result,
        pipeline_latency_ms=elapsed,
        warnings=warnings,
    )


def run_pipeline_batch(patients: list[PatientData],
                       **kwargs) -> list[PipelineResult]:
    """Run pipeline on multiple patients sequentially."""
    return [run_pipeline(p, **kwargs) for p in patients]
