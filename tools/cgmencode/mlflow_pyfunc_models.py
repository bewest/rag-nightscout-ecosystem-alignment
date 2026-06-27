"""Minimal MLflow pyfunc models for structured physiology-model pilots."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .parameter_model_bundle import PERIOD_ALIASES, load_bundle

try:
    import mlflow  # type: ignore
except ImportError:  # pragma: no cover - optional at runtime
    mlflow = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional at runtime
    pd = None


_PyfuncBase = mlflow.pyfunc.PythonModel if mlflow is not None else object


def _normalize_rows(model_input: Any) -> list[dict[str, Any]]:
    if pd is not None and isinstance(model_input, pd.DataFrame):
        return model_input.to_dict(orient='records')
    if isinstance(model_input, dict):
        return [model_input]
    if isinstance(model_input, list):
        return [dict(item) if isinstance(item, dict) else {'value': item} for item in model_input]
    raise TypeError(f'Unsupported model input type: {type(model_input)!r}')


def build_input_example():
    rows = [{
        'patient_id': 'patient-a',
        'profile_isf': 42.0,
        'observed_isf': 58.0,
        'correction_ratio': 1.25,
        'overnight_drift_mgdl_per_hour': 6.0,
        'time_of_day': 'overnight',
    }]
    if pd is not None:
        return pd.DataFrame(rows)
    return rows


def _resolve_time_block(
    time_of_day: str | None,
    schedule: dict[str, Any],
) -> str | None:
    if not time_of_day or not schedule:
        return None
    lowered = str(time_of_day).strip().lower()
    if lowered in PERIOD_ALIASES and PERIOD_ALIASES[lowered] in schedule:
        return PERIOD_ALIASES[lowered]
    if lowered in schedule:
        return lowered
    return None


class EffectiveParameterExtractorModel(_PyfuncBase):
    """Registration-ready pilot model for effective parameter extraction.

    This is intentionally simple. It demonstrates a stable callable interface
    for a learned-physiology object before deeper research models are promoted.
    """

    def __init__(
        self,
        candidate: dict[str, Any] | None = None,
        *,
        bundle: dict[str, Any] | None = None,
    ):
        self.candidate = candidate or {}
        self.bundle = bundle or {}

    def load_context(self, context) -> None:  # pragma: no cover - exercised via mlflow load
        candidate_path = context.artifacts.get('candidate_json') if context else None
        if candidate_path:
            self.candidate = json.loads(Path(candidate_path).read_text(encoding='utf-8'))
        bundle_path = context.artifacts.get('bundle_json') if context else None
        if bundle_path:
            self.bundle = load_bundle(bundle_path)

    def predict(self, context, model_input):  # type: ignore[override]
        rows = _normalize_rows(model_input)
        outputs: list[dict[str, Any]] = []
        readiness = (
            self.candidate.get('evaluation_summary', {}).get('readiness')
            or self.candidate.get('registration_readiness')
            or 'candidate'
        )
        confidence = (
            self.candidate.get('evaluation_summary', {}).get('readiness_score')
            or 0.5
        )
        titration_guidance = self.candidate.get('titration_guidance', {})
        titration_plan = self.candidate.get('titration_plan', {})
        patient_models = self.bundle.get('patient_models', {})
        population_ratio = (
            self.bundle.get('training_summary', {}).get('population_median_ratio')
            or self.candidate.get('evaluation_summary', {}).get('readiness_score')
            or 1.0
        )
        for row in rows:
            patient_id = row.get('patient_id')
            profile_isf = float(row.get('profile_isf', 45.0))
            observed_isf = row.get('observed_isf')
            overnight_drift = float(row.get('overnight_drift_mgdl_per_hour', 0.0))
            time_of_day = row.get('time_of_day')
            patient_plan = titration_plan.get('per_patient', {}).get(str(patient_id), {})
            patient_model = patient_models.get(str(patient_id)) if patient_id is not None else None
            if patient_model:
                schedule_model = patient_model.get('isf_schedule_model', {})
                optimized_schedule = schedule_model.get('optimized_schedule', {})
                block = _resolve_time_block(time_of_day, optimized_schedule)
                if block:
                    effective_isf = round(float(optimized_schedule[block]), 1)
                    source = 'patient-isf-schedule'
                else:
                    effective_isf = round(float(patient_model['effective_isf']), 1)
                    source = 'patient-bundle'
                patient_ratio = float(patient_model.get('isf_ratio', population_ratio))
                basal_period = patient_model.get('basal_period_model', {})
                periods = basal_period.get('periods', {})
                period_key = None
                if time_of_day:
                    period_key = str(time_of_day).strip().lower()
                if period_key in periods:
                    period = periods[period_key]
                    mean_dbg = float(period.get('mean_fasting_dbg', 0.0))
                    basal_adjustment_signal = round(max(-0.5, min(0.5, mean_dbg / 10.0)), 3)
                else:
                    basal_adjustment_signal = round(max(-0.5, min(0.5, (patient_ratio - 1.0) / 2.0)), 3)
            else:
                if observed_isf is not None:
                    effective_isf = round(float(observed_isf), 1)
                    source = 'observed-input'
                else:
                    effective_isf = round(profile_isf * float(population_ratio), 1)
                    source = 'population-bundle'
                basal_adjustment_signal = round(max(-0.5, min(0.5, overnight_drift / 20.0)), 3)
            outputs.append({
                'effective_isf_estimate': effective_isf,
                'basal_adjustment_signal': basal_adjustment_signal,
                'isf_source': source,
                'recommended_action': (
                    'review-and-validate'
                    if readiness == 'candidate'
                    else 'gather-more-evidence'
                ),
                'confidence_score': round(float(confidence), 3),
                'model_candidate_name': self.candidate.get('candidate_name', 'effective-parameter-extractor'),
                'needs_adjustment_periods': patient_model.get('basal_period_model', {}).get('needs_adjustment', []) if patient_model else [],
                'max_basal_step_pct': titration_guidance.get('max_basal_step_pct'),
                'reassessment_days': titration_guidance.get('reassessment_days'),
                'concurrent_change_review_required': titration_guidance.get('concurrent_change_review_required'),
                'policy_recommendation': titration_guidance.get('promotion_recommendation'),
                'staged_action': patient_plan.get('staged_action'),
                'review_required': patient_plan.get('review_required'),
                'suggested_basal_step_pct': patient_plan.get('suggested_basal_step_pct'),
            })
        if pd is not None:
            return pd.DataFrame(outputs)
        return outputs


def save_effective_parameter_extractor_model(
    output_path: str | Path,
    candidate: dict[str, Any],
) -> str | None:
    if mlflow is None:
        return None
    output_path = Path(output_path)
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path = output_path.parent / f'{output_path.name}_candidate.json'
    candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True), encoding='utf-8')
    bundle_path = candidate.get('bundle_path')
    artifacts = {'candidate_json': str(candidate_path)}
    model_bundle = None
    if bundle_path:
        artifacts['bundle_json'] = str(bundle_path)
        model_bundle = load_bundle(bundle_path)
    mlflow.pyfunc.save_model(
        path=str(output_path),
        python_model=EffectiveParameterExtractorModel(candidate, bundle=model_bundle),
        artifacts=artifacts,
        input_example=build_input_example(),
    )
    return str(output_path)
