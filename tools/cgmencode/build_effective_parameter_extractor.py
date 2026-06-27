#!/usr/bin/env python3
"""Build a canonical effective-parameter-extractor model package from validation results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mlflow_pyfunc_models import save_effective_parameter_extractor_model
from .parameter_model_bundle import (
    derive_titration_plan,
    derive_titration_guidance,
    build_effective_parameter_bundle,
    assess_effective_parameter_thresholds,
    evaluate_effective_parameter_bundle,
    propose_effective_parameter_thresholds,
    save_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VALIDATION_RESULTS = ROOT / 'visualizations' / 'clinical-validation' / 'validation_results.json'
DEFAULT_OUTPUT_DIR = ROOT / 'externals' / 'experiments' / 'parameter-models'
DEFAULT_SCORE_TIR = ROOT / 'externals' / 'experiments' / 'exp581_score_predicts_future_tir.json'
DEFAULT_BASAL_DECOMP = ROOT / 'externals' / 'experiments' / 'exp582_per-period_basal_decomposition.json'
DEFAULT_ISF_SCHEDULE = ROOT / 'externals' / 'experiments' / 'exp_773_exp-773_isf_schedule_optimizer.json'
DEFAULT_BASAL_SCHEDULE = ROOT / 'externals' / 'experiments' / 'exp_774_exp-774_basal_schedule_optimizer.json'


def _load_json_if_exists(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-results', default=str(DEFAULT_VALIDATION_RESULTS))
    parser.add_argument('--output-dir', default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument('--name', default='effective-parameter-extractor')
    parser.add_argument('--score-tir', default=str(DEFAULT_SCORE_TIR))
    parser.add_argument('--basal-decomposition', default=str(DEFAULT_BASAL_DECOMP))
    parser.add_argument('--isf-schedule', default=str(DEFAULT_ISF_SCHEDULE))
    parser.add_argument('--basal-schedule', default=str(DEFAULT_BASAL_SCHEDULE))
    args = parser.parse_args()

    validation_path = Path(args.validation_results)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = json.loads(validation_path.read_text(encoding='utf-8'))
    bundle = build_effective_parameter_bundle(
        results,
        source_path=str(validation_path),
        score_predicts_future_tir=_load_json_if_exists(Path(args.score_tir)),
        basal_decomposition=_load_json_if_exists(Path(args.basal_decomposition)),
        isf_schedule_optimizer=_load_json_if_exists(Path(args.isf_schedule)),
        basal_schedule_optimizer=_load_json_if_exists(Path(args.basal_schedule)),
    )
    bundle_path = save_bundle(bundle, output_dir / f'{args.name}_bundle.json')
    evaluation = evaluate_effective_parameter_bundle(bundle)
    evaluation_path = save_bundle(evaluation, output_dir / f'{args.name}_evaluation.json')
    thresholds = propose_effective_parameter_thresholds(evaluation)
    thresholds_path = save_bundle(thresholds, output_dir / f'{args.name}_thresholds.json')
    assessment = assess_effective_parameter_thresholds(evaluation, thresholds)
    assessment_path = save_bundle(assessment, output_dir / f'{args.name}_assessment.json')
    guidance = derive_titration_guidance(evaluation, assessment)
    guidance_path = save_bundle(guidance, output_dir / f'{args.name}_guidance.json')
    plan = derive_titration_plan(bundle, evaluation, assessment, guidance)
    plan_path = save_bundle(plan, output_dir / f'{args.name}_plan.json')
    model_path = output_dir / f'{args.name}_model'
    save_effective_parameter_extractor_model(
        model_path,
        {
            'bundle_path': str(bundle_path),
            'bundle_evaluation_path': str(evaluation_path),
            'bundle_evaluation': evaluation,
            'thresholds_path': str(thresholds_path),
            'threshold_assessment_path': str(assessment_path),
            'threshold_assessment': assessment,
            'guidance_path': str(guidance_path),
            'titration_guidance': guidance,
            'plan_path': str(plan_path),
            'titration_plan': plan,
        },
    )

    print(f'Bundle: {bundle_path}')
    print(f'Evaluation: {evaluation_path}')
    print(f'Thresholds: {thresholds_path}')
    print(f'Assessment: {assessment_path}')
    print(f'Guidance: {guidance_path}')
    print(f'Plan: {plan_path}')
    print(f'Model: {model_path}')


if __name__ == '__main__':
    main()
