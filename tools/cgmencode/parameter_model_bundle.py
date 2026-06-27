"""Canonical learned-artifact bundles for structured physiology models."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = '1.0'
PERIOD_ALIASES = {
    'overnight': '00:00',
    'morning': '08:00',
    'afternoon': '12:00',
    'evening': '20:00',
}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_effective_parameter_bundle(
    validation_results: dict[str, Any],
    *,
    source_path: str | None = None,
    score_predicts_future_tir: dict[str, Any] | None = None,
    basal_decomposition: dict[str, Any] | None = None,
    isf_schedule_optimizer: dict[str, Any] | None = None,
    basal_schedule_optimizer: dict[str, Any] | None = None,
    carb_ratio_analysis: dict[str, Any] | None = None,
    dose_dependent_cr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patient_models: dict[str, dict[str, Any]] = {}
    ratios: list[float] = []
    effective_isfs: list[float] = []
    profile_isfs: list[float] = []

    for patient_id, raw in sorted(validation_results.items()):
        if not isinstance(raw, dict) or raw.get('error'):
            continue
        effective_isf = _safe_float(raw.get('effective_isf'))
        profile_isf = _safe_float(raw.get('profile_isf'))
        isf_discrepancy = _safe_float(raw.get('isf_discrepancy'))
        if effective_isf is None or profile_isf is None:
            continue
        ratio = isf_discrepancy
        if ratio is None and profile_isf:
            ratio = effective_isf / profile_isf
        if ratio is None:
            continue

        confidence_grade = raw.get('ada_grade') or raw.get('fidelity_grade') or 'unknown'
        patient_models[patient_id] = {
            'effective_isf': effective_isf,
            'profile_isf': profile_isf,
            'isf_ratio': ratio,
            'tir': _safe_float(raw.get('tir')),
            'tbr': _safe_float(raw.get('tbr')),
            'tar': _safe_float(raw.get('tar')),
            'confidence_grade': confidence_grade,
            'units': raw.get('units', 'mg/dL'),
        }
        ratios.append(ratio)
        effective_isfs.append(effective_isf)
        profile_isfs.append(profile_isf)

    if not patient_models:
        raise ValueError('No usable patient models found in validation results')

    ratio_sorted = sorted(ratios)
    if score_predicts_future_tir:
        for patient_id, raw in score_predicts_future_tir.get('patients', {}).items():
            patient = patient_models.get(patient_id)
            if not patient or not isinstance(raw, dict):
                continue
            patient['settings_score_signal'] = {
                'n_months': raw.get('n_months'),
                'r_score_tir_change': _safe_float(raw.get('r_score_tir_change')),
                'low_score_tir_change': _safe_float(raw.get('low_score_tir_change')),
                'high_score_tir_change': _safe_float(raw.get('high_score_tir_change')),
            }

    if basal_decomposition:
        for patient_id, raw in basal_decomposition.get('patients', {}).items():
            patient = patient_models.get(patient_id)
            if not patient or not isinstance(raw, dict):
                continue
            patient['basal_period_model'] = {
                'worst_period': raw.get('worst_period'),
                'needs_adjustment': list(raw.get('needs_adjustment', [])),
                'n_adjustments': raw.get('n_adjustments'),
                'periods': raw.get('periods', {}),
            }

    if isf_schedule_optimizer:
        for raw in isf_schedule_optimizer.get('per_patient', []):
            patient_id = raw.get('patient')
            patient = patient_models.get(patient_id)
            if not patient or not isinstance(raw, dict):
                continue
            patient['isf_schedule_model'] = {
                'current_isf': _safe_float(raw.get('current_isf')),
                'optimized_schedule': raw.get('optimized_schedule', {}),
                'variation_pct': _safe_float(raw.get('variation_pct')),
                'n_blocks': raw.get('n_blocks'),
            }

    if basal_schedule_optimizer:
        for raw in basal_schedule_optimizer.get('per_patient', []):
            patient_id = raw.get('patient')
            patient = patient_models.get(patient_id)
            if not patient or not isinstance(raw, dict):
                continue
            patient['basal_schedule_model'] = {
                'current_basal': _safe_float(raw.get('current_basal')),
                'max_adj_pct': _safe_float(raw.get('max_adj_pct')),
                'schedule': raw.get('schedule', {}),
                'n_blocks': raw.get('n_blocks'),
            }

    if carb_ratio_analysis:
        patient_payload = carb_ratio_analysis.get('patients')
        if isinstance(patient_payload, dict):
            for patient_id, raw in patient_payload.items():
                patient = patient_models.get(patient_id)
                if not patient or not isinstance(raw, dict):
                    continue
                patient['carb_ratio_model'] = {
                    'profile_cr': _safe_float(raw.get('profile_cr')),
                    'observed_cr': _safe_float(raw.get('observed_cr')),
                    'deconfounded_cr': _safe_float(raw.get('deconfounded_cr')),
                    'recommended_cr': _safe_float(raw.get('recommended_cr')),
                    'n_events': raw.get('n_events'),
                }

    if dose_dependent_cr:
        patient_payload = dose_dependent_cr.get('per_patient')
        if isinstance(patient_payload, list):
            for raw in patient_payload:
                patient_id = raw.get('patient_id') or raw.get('patient')
                patient = patient_models.get(patient_id)
                if not patient or not isinstance(raw, dict):
                    continue
                patient.setdefault('carb_ratio_model', {})
                patient['carb_ratio_model']['dose_dependent'] = {
                    'significant': raw.get('significant'),
                    'median_cr_small': _safe_float(raw.get('median_cr_small')),
                    'median_cr_large': _safe_float(raw.get('median_cr_large')),
                    'cr_ratio_large_small': _safe_float(raw.get('cr_ratio_large_small')),
                }

    bundle = {
        'schema_version': SCHEMA_VERSION,
        'bundle_type': 'effective-parameter-extractor',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_artifact': source_path,
        'upstream_artifacts': {
            'score_predicts_future_tir': bool(score_predicts_future_tir),
            'basal_decomposition': bool(basal_decomposition),
            'isf_schedule_optimizer': bool(isf_schedule_optimizer),
            'basal_schedule_optimizer': bool(basal_schedule_optimizer),
            'carb_ratio_analysis': bool(carb_ratio_analysis),
            'dose_dependent_cr': bool(dose_dependent_cr),
        },
        'training_summary': {
            'n_patients': len(patient_models),
            'population_median_effective_isf': statistics.median(effective_isfs),
            'population_median_profile_isf': statistics.median(profile_isfs),
            'population_median_ratio': statistics.median(ratios),
            'population_min_ratio': ratio_sorted[0],
            'population_max_ratio': ratio_sorted[-1],
        },
        'artifact_contract': {
            'inputs': ['patient_id', 'profile_isf', 'time_of_day'],
            'optional_inputs': ['observed_isf', 'overnight_drift_mgdl_per_hour'],
            'outputs': [
                'effective_isf_estimate',
                'isf_source',
                'confidence_score',
                'basal_adjustment_signal',
            ],
        },
        'patient_models': patient_models,
    }
    bundle['settings_special_handling'] = derive_settings_special_handling(
        bundle,
        carb_ratio_analysis=carb_ratio_analysis,
        dose_dependent_cr=dose_dependent_cr,
    )
    return bundle


def evaluate_effective_parameter_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    patient_models = bundle.get('patient_models', {})
    n_patients = len(patient_models)
    if n_patients == 0:
        raise ValueError('Bundle contains no patient models')

    ratios = []
    abs_isf_deltas = []
    tbr_values = []
    tir_values = []
    schedule_coverage = 0
    basal_schedule_coverage = 0
    basal_period_coverage = 0
    score_signal_coverage = 0
    aggressive_basal_count = 0
    basal_over_ten_pct_count = 0
    high_variation_count = 0
    recommended_adjustment_count = 0
    concurrent_change_count = 0
    projected_tir_effects = []

    for patient in patient_models.values():
        ratio = _safe_float(patient.get('isf_ratio'))
        effective_isf = _safe_float(patient.get('effective_isf'))
        profile_isf = _safe_float(patient.get('profile_isf'))
        tbr = _safe_float(patient.get('tbr'))
        tir = _safe_float(patient.get('tir'))
        if ratio is not None:
            ratios.append(ratio)
        if effective_isf is not None and profile_isf is not None:
            abs_isf_deltas.append(abs(effective_isf - profile_isf))
        if tbr is not None:
            tbr_values.append(tbr)
        if tir is not None:
            tir_values.append(tir)

        if patient.get('isf_schedule_model'):
            schedule_coverage += 1
            variation_pct = _safe_float(patient['isf_schedule_model'].get('variation_pct'))
            if variation_pct is not None and variation_pct > 25:
                high_variation_count += 1

        if patient.get('basal_schedule_model'):
            basal_schedule_coverage += 1
            max_adj_pct = _safe_float(patient['basal_schedule_model'].get('max_adj_pct'))
            if max_adj_pct is not None and abs(max_adj_pct) > 50:
                aggressive_basal_count += 1
            if max_adj_pct is not None and abs(max_adj_pct) > 10:
                basal_over_ten_pct_count += 1

        if patient.get('basal_period_model'):
            basal_period_coverage += 1
            n_adjustments = patient['basal_period_model'].get('n_adjustments') or 0
            if n_adjustments:
                recommended_adjustment_count += 1

        has_isf_change_signal = bool(patient.get('isf_schedule_model')) or (
            ratio is not None and abs(ratio - 1.0) > 0.1
        )
        has_basal_change_signal = bool(patient.get('basal_schedule_model')) or bool(patient.get('basal_period_model'))
        if has_isf_change_signal and has_basal_change_signal:
            concurrent_change_count += 1

        if patient.get('settings_score_signal'):
            score_signal_coverage += 1
            low = _safe_float(patient['settings_score_signal'].get('low_score_tir_change'))
            high = _safe_float(patient['settings_score_signal'].get('high_score_tir_change'))
            if low is not None and high is not None:
                projected_tir_effects.append(high - low)

    descriptive = {
        'n_patients': n_patients,
        'median_isf_ratio': statistics.median(ratios) if ratios else None,
        'median_abs_isf_delta_mgdl': statistics.median(abs_isf_deltas) if abs_isf_deltas else None,
        'schedule_coverage_fraction': round(schedule_coverage / n_patients, 3),
        'basal_schedule_coverage_fraction': round(basal_schedule_coverage / n_patients, 3),
    }
    prescriptive = {
        'basal_period_coverage_fraction': round(basal_period_coverage / n_patients, 3),
        'settings_score_signal_fraction': round(score_signal_coverage / n_patients, 3),
        'patients_with_adjustments_fraction': round(recommended_adjustment_count / n_patients, 3),
        'median_projected_tir_effect': (
            statistics.median(projected_tir_effects) if projected_tir_effects else None
        ),
    }
    safety = {
        'median_tbr': statistics.median(tbr_values) if tbr_values else None,
        'median_tir': statistics.median(tir_values) if tir_values else None,
        'aggressive_basal_fraction': round(aggressive_basal_count / n_patients, 3),
        'basal_over_ten_pct_fraction': round(basal_over_ten_pct_count / n_patients, 3),
        'high_isf_variation_fraction': round(high_variation_count / n_patients, 3),
        'concurrent_change_fraction': round(concurrent_change_count / n_patients, 3),
    }
    return {
        'schema_version': SCHEMA_VERSION,
        'evaluation_type': 'effective-parameter-extractor',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'descriptive': descriptive,
        'prescriptive': prescriptive,
        'safety': safety,
    }


def propose_effective_parameter_thresholds(
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    descriptive = evaluation.get('descriptive', {})
    prescriptive = evaluation.get('prescriptive', {})
    safety = evaluation.get('safety', {})

    proposal = {
        'schema_version': SCHEMA_VERSION,
        'proposal_type': 'effective-parameter-extractor-thresholds',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'evidence_basis': [
            'settings optimization guide: 25% max change per cycle, full confidence at 14+ days',
            'validated research: temporal stability and zero-overfitting expectations',
            'safety evidence: naive ISF replacement can increase TBR materially',
            'user titration policy: basal changes are often limited to about 10% with reassessment every few days; concurrent basal and ISF changes require extra caution',
        ],
        'gates': {
            'descriptive': {
                'schedule_coverage_fraction_min': 0.8,
                'basal_schedule_coverage_fraction_min': 0.8,
                'median_abs_isf_delta_mgdl_max': 80.0,
            },
            'prescriptive': {
                'basal_period_coverage_fraction_min': 0.7,
                'settings_score_signal_fraction_min': 0.5,
                'patients_with_adjustments_fraction_min': 0.5,
            },
            'safety': {
                'median_tbr_max': 0.04,
                'aggressive_basal_fraction_max': 0.25,
                'high_isf_variation_fraction_max': 0.6,
                'basal_over_ten_pct_fraction_max': 0.1,
                'concurrent_change_fraction_max': 0.0,
            },
        },
        'current_metrics': {
            'descriptive': descriptive,
            'prescriptive': prescriptive,
            'safety': safety,
        },
    }
    return proposal


def assess_effective_parameter_thresholds(
    evaluation: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    gates = thresholds.get('gates', {})
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    missing_metrics: list[str] = []
    advisory_warnings: list[str] = []

    def check(section: str, metric: str, direction: str, threshold_value: float):
        value = evaluation.get(section, {}).get(metric)
        status = 'pass'
        if value is None:
            status = 'missing'
        elif direction == 'min' and value < threshold_value:
            status = 'fail'
        elif direction == 'max' and value > threshold_value:
            status = 'fail'

        # Concurrent basal+ISF adjustments are often necessary, but should
        # normally require review only when they are paired with large basal
        # changes. Keep them visible without auto-failing safe small titrations.
        if section == 'safety' and metric == 'concurrent_change_fraction' and status == 'fail':
            basal_over_ten = evaluation.get('safety', {}).get('basal_over_ten_pct_fraction')
            aggressive_basal = evaluation.get('safety', {}).get('aggressive_basal_fraction')
            if (
                basal_over_ten is not None and aggressive_basal is not None
                and basal_over_ten <= 0.1 and aggressive_basal <= 0.25
            ):
                status = 'warn'

        results.append({
            'section': section,
            'metric': metric,
            'direction': direction,
            'threshold': threshold_value,
            'value': value,
            'status': status,
        })
        if status == 'fail':
            failures.append(f'{section}.{metric}')
        elif status == 'missing':
            missing_metrics.append(f'{section}.{metric}')
        elif status == 'warn':
            advisory_warnings.append(f'{section}.{metric}')

    for metric, threshold_value in gates.get('descriptive', {}).items():
        direction = 'min' if metric.endswith('_min') else 'max'
        metric_name = metric.rsplit('_', 1)[0]
        check('descriptive', metric_name, direction, threshold_value)
    for metric, threshold_value in gates.get('prescriptive', {}).items():
        direction = 'min' if metric.endswith('_min') else 'max'
        metric_name = metric.rsplit('_', 1)[0]
        check('prescriptive', metric_name, direction, threshold_value)
    for metric, threshold_value in gates.get('safety', {}).items():
        direction = 'min' if metric.endswith('_min') else 'max'
        metric_name = metric.rsplit('_', 1)[0]
        check('safety', metric_name, direction, threshold_value)

    safety_failures = [item for item in failures if item.startswith('safety.')]
    if safety_failures:
        recommendation = 'needs-review'
    elif failures:
        recommendation = 'candidate'
    elif missing_metrics:
        recommendation = 'candidate'
    else:
        recommendation = 'validated'

    return {
        'schema_version': SCHEMA_VERSION,
        'assessment_type': 'effective-parameter-extractor-thresholds',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'results': results,
        'failed_gates': failures,
        'missing_metrics': missing_metrics,
        'advisory_warnings': advisory_warnings,
        'promotion_recommendation': recommendation,
    }


def derive_titration_guidance(
    evaluation: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, Any]:
    safety = evaluation.get('safety', {})
    basal_over_ten = safety.get('basal_over_ten_pct_fraction')
    concurrent_change = safety.get('concurrent_change_fraction')
    recommendation = assessment.get('promotion_recommendation', 'candidate')

    review_required = recommendation == 'needs-review'
    max_basal_step_pct = 10
    reassessment_days = 3 if review_required else 5

    return {
        'schema_version': SCHEMA_VERSION,
        'guidance_type': 'effective-parameter-extractor-titration',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'max_basal_step_pct': max_basal_step_pct,
        'reassessment_days': reassessment_days,
        'concurrent_change_review_required': bool(
            concurrent_change is not None and concurrent_change > 0
        ),
        'promotion_recommendation': recommendation,
        'notes': [
            'Limit basal changes to about 10% per titration cycle.',
            'When basal and ISF both need adjustment, prefer explicit review before applying both together.',
            'Reassess after a few days before further titration.',
        ],
        'current_policy_flags': {
            'basal_over_ten_pct_fraction': basal_over_ten,
            'concurrent_change_fraction': concurrent_change,
            'review_required': review_required,
        },
    }


def derive_settings_special_handling(
    bundle: dict[str, Any],
    *,
    carb_ratio_analysis: dict[str, Any] | None = None,
    dose_dependent_cr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patient_models = bundle.get('patient_models', {})
    n_patients = max(1, len(patient_models))
    training_summary = bundle.get('training_summary', {})

    isf_schedule_patients = sum(1 for patient in patient_models.values() if patient.get('isf_schedule_model'))
    basal_schedule_patients = sum(1 for patient in patient_models.values() if patient.get('basal_schedule_model'))
    basal_period_patients = sum(1 for patient in patient_models.values() if patient.get('basal_period_model'))
    carb_ratio_patients = sum(1 for patient in patient_models.values() if patient.get('carb_ratio_model'))

    carb_ratio_patient_payload = carb_ratio_analysis.get('patients') if carb_ratio_analysis else None
    if isinstance(carb_ratio_patient_payload, dict):
        carb_ratio_patients = max(carb_ratio_patients, len(carb_ratio_patient_payload))

    dose_dep_ratio = None
    dose_dep_r = None
    if dose_dependent_cr:
        aggregate = dose_dependent_cr.get('aggregate', {})
        if isinstance(aggregate, dict):
            dose_dep_ratio = _safe_float(aggregate.get('median_cr_ratio_large_small'))
            dose_dep_r = _safe_float(aggregate.get('mean_r_carbs_cr'))
    announced_meal_dependency = bool(carb_ratio_analysis or dose_dependent_cr)

    return {
        'schema_version': SCHEMA_VERSION,
        'summary_type': 'settings-extraction-special-handling',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'settings': {
            'isf': {
                'extraction_target': 'controller-aware predictive ISF, not direct physiological truth',
                'coverage_fraction': round(isf_schedule_patients / n_patients, 3),
                'special_handling': [
                    'Treat the profile-vs-observed ISF gap as partly intentional controller safety margin.',
                    'Prefer correction-event and counterfactual framing over raw observed-outcome interpretation.',
                    'Review large ISF schedule variation before promoting direct schedule changes.',
                ],
                'evidence': {
                    'population_median_ratio': training_summary.get('population_median_ratio'),
                    'population_min_ratio': training_summary.get('population_min_ratio'),
                    'population_max_ratio': training_summary.get('population_max_ratio'),
                    'isf_schedule_patients': isf_schedule_patients,
                },
            },
            'basal': {
                'extraction_target': 'time-of-day basal tuning with capped staged titration',
                'coverage_fraction': round(max(basal_schedule_patients, basal_period_patients) / n_patients, 3),
                'special_handling': [
                    'Basal adjustments should be localized by period instead of forced into a global score.',
                    'Cap basal steps and reassess before compounding changes.',
                    'Escalate explicit review when basal and ISF both signal change pressure.',
                ],
                'evidence': {
                    'basal_schedule_patients': basal_schedule_patients,
                    'basal_period_patients': basal_period_patients,
                },
            },
            'carb_ratio': {
                'extraction_target': 'meal-independent carb coverage proxy with deconfounding and meal-size awareness',
                'coverage_fraction': round(carb_ratio_patients / n_patients, 3) if carb_ratio_patients else 0.0,
                'special_handling': [
                    'Do not require announced meals as the long-term dependency for CR support.',
                    'Treat meal-announcement-derived CR estimates as provisional evidence, not promotion-ready truth.',
                    'Check whether carb ratio changes with meal size before promoting one flat CR.',
                    'Avoid changing CR at the same time as major basal or ISF changes unless explicitly reviewed.',
                ],
                'evidence_loaded': {
                    'carb_ratio_analysis': bool(carb_ratio_analysis),
                    'dose_dependent_cr': bool(dose_dependent_cr),
                    'depends_on_announced_meals': announced_meal_dependency,
                },
                'evidence': {
                    'carb_ratio_patients': carb_ratio_patients,
                    'median_large_small_ratio': dose_dep_ratio,
                    'meal_size_dependence_r': dose_dep_r,
                },
                'promotion_ready_without_meals': False if announced_meal_dependency else None,
            },
        },
        'combined_cautions': [
            'Basal, ISF, and carb ratio should not be treated as interchangeable settings-extraction problems.',
            'Observed optimal settings can be controller-mediated, so causal interpretation needs setting-specific checks.',
            'Settings extraction should not depend on announced meals if the intended workflow must work when meals are unlogged.',
            'When multiple settings change together, stage the intervention or require explicit review.',
        ],
    }


def derive_titration_plan(
    bundle: dict[str, Any],
    evaluation: dict[str, Any],
    assessment: dict[str, Any],
    guidance: dict[str, Any],
) -> dict[str, Any]:
    patient_models = bundle.get('patient_models', {})
    max_basal_step_pct = guidance.get('max_basal_step_pct', 10)
    reassessment_days = guidance.get('reassessment_days', 3)
    per_patient: dict[str, Any] = {}

    for patient_id, patient in sorted(patient_models.items()):
        isf_ratio = _safe_float(patient.get('isf_ratio')) or 1.0
        has_isf_change_signal = bool(patient.get('isf_schedule_model')) or abs(isf_ratio - 1.0) > 0.1
        basal_schedule = patient.get('basal_schedule_model', {})
        max_adj_pct = _safe_float(basal_schedule.get('max_adj_pct'))
        basal_period = patient.get('basal_period_model', {})
        has_basal_change_signal = bool(basal_schedule) or bool(basal_period.get('needs_adjustment'))
        concurrent = has_isf_change_signal and has_basal_change_signal
        basal_over_ten = max_adj_pct is not None and abs(max_adj_pct) > max_basal_step_pct

        if concurrent and basal_over_ten:
            staged_action = 'review-basal-first'
            notes = [
                'Basal and ISF both show change pressure.',
                'Cap basal change to the policy step size before considering ISF changes.',
                f'Recheck after {reassessment_days} days before the next step.',
            ]
        elif concurrent:
            staged_action = 'lockstep-review'
            notes = [
                'Basal and ISF both show change pressure.',
                'Concurrent changes may be necessary, but require explicit review.',
                f'Use no more than {max_basal_step_pct}% basal change, then reassess after {reassessment_days} days.',
            ]
        elif has_basal_change_signal:
            staged_action = 'basal-first'
            notes = [
                f'Apply at most {max_basal_step_pct}% basal change in this cycle.',
                f'Reassess after {reassessment_days} days before further titration.',
            ]
        elif has_isf_change_signal:
            staged_action = 'isf-review'
            notes = [
                'ISF signal present without strong basal change pressure.',
                f'Reassess after {reassessment_days} days after any change.',
            ]
        else:
            staged_action = 'observe'
            notes = ['No strong change signal detected. Continue observation and reassess on the normal cadence.']

        per_patient[patient_id] = {
            'staged_action': staged_action,
            'review_required': guidance.get('promotion_recommendation') == 'needs-review' or concurrent,
            'concurrent_change_signal': concurrent,
            'basal_change_signal': has_basal_change_signal,
            'isf_change_signal': has_isf_change_signal,
            'max_basal_step_pct': max_basal_step_pct,
            'suggested_basal_step_pct': min(abs(max_adj_pct), max_basal_step_pct) if max_adj_pct is not None else None,
            'reassessment_days': reassessment_days,
            'notes': notes,
        }

    return {
        'schema_version': SCHEMA_VERSION,
        'plan_type': 'effective-parameter-extractor-remediation',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'promotion_recommendation': assessment.get('promotion_recommendation'),
        'per_patient': per_patient,
    }


def save_bundle(bundle: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding='utf-8')
    return path


def load_bundle(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding='utf-8'))
