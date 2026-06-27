#!/usr/bin/env python3
"""Minimal traced autoresearch pilot for decision-support workflows.

This pilot does not require an external LLM key. It prepares a structured
research memo by retrieving local evidence, suggesting follow-up experiments,
and logging the workflow to MLflow using standard runs plus nested spans.

Usage:
    python3 -m tools.cgmencode.autoresearch_agent --direction parameter-extraction
    python3 -m tools.cgmencode.autoresearch_agent --direction intervention-scoring
    python3 -m tools.cgmencode.autoresearch_agent --direction deconfounding-audit
"""

from __future__ import annotations

import argparse
import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mlflow_utils import (
    build_run_context,
    log_artifact,
    log_dict,
    log_metrics,
    log_model_artifact,
    log_pyfunc_model,
    log_run_context,
    start_run,
)
from .mlflow_pyfunc_models import (
    build_input_example,
    EffectiveParameterExtractorModel,
    save_effective_parameter_extractor_model,
)
from .parameter_model_bundle import (
    derive_titration_plan,
    derive_titration_guidance,
    assess_effective_parameter_thresholds,
    build_effective_parameter_bundle,
    evaluate_effective_parameter_bundle,
    propose_effective_parameter_thresholds,
    save_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / 'externals' / 'experiments' / 'autoresearch'
RECENT_SWEEP = ROOT / 'externals' / 'experiments' / 'mlflow-initial-quick_results.json'
DEFAULT_VALIDATION_RESULTS = ROOT / 'visualizations' / 'clinical-validation' / 'validation_results.json'
DEFAULT_SCORE_TIR = ROOT / 'externals' / 'experiments' / 'exp581_score_predicts_future_tir.json'
DEFAULT_BASAL_DECOMP = ROOT / 'externals' / 'experiments' / 'exp582_per-period_basal_decomposition.json'
DEFAULT_ISF_SCHEDULE = ROOT / 'externals' / 'experiments' / 'exp_773_exp-773_isf_schedule_optimizer.json'
DEFAULT_BASAL_SCHEDULE = ROOT / 'externals' / 'experiments' / 'exp_774_exp-774_basal_schedule_optimizer.json'
DEFAULT_CARB_RATIO = ROOT / 'externals' / 'experiments' / 'exp-2729_carb_ratio.json'
DEFAULT_DOSE_DEPENDENT_CR = ROOT / 'externals' / 'experiments' / 'exp-2747_dose_dependent_cr.json'

try:
    import mlflow  # type: ignore
except ImportError:  # pragma: no cover - optional at runtime
    mlflow = None


class _NullSpan:
    def set_inputs(self, *_args, **_kwargs):
        return None

    def set_outputs(self, *_args, **_kwargs):
        return None

    def set_attributes(self, *_args, **_kwargs):
        return None


@contextmanager
def _span(name: str, span_type: str = 'AGENT', attributes: dict[str, Any] | None = None):
    if mlflow is None:
        yield _NullSpan()
        return
    with mlflow.start_span(name=name, span_type=span_type, attributes=attributes or {}) as span:
        yield span


@dataclass(frozen=True)
class DirectionSpec:
    key: str
    title: str
    default_question: str
    search_terms: tuple[str, ...]
    candidate_files: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    hypotheses: tuple[str, ...]
    success_criteria: tuple[str, ...]


DIRECTIONS: dict[str, DirectionSpec] = {
    'parameter-extraction': DirectionSpec(
        key='parameter-extraction',
        title='Effective Parameter Extraction from History',
        default_question=(
            'Using prior ISF, drift, override, and phenotype work, identify the '
            'strongest method for extracting effective parameters from history '
            'and propose a validation follow-up.'
        ),
        search_terms=('isf', 'drift', 'override', 'counterfactual', 'effective_isf', 'phenotype'),
        candidate_files=(
            'tools/cgmencode/experiments_validated.py',
            'tools/cgmencode/run_pattern_experiments.py',
            'tools/cgmencode/run_validation_report.py',
            'tools/cgmencode/QUICK_REFERENCE.md',
            'tools/cgmencode/EXP-2895-2900_AUTORESEARCH_PIPELINE.md',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.run_pattern_experiments isf-response-ratio',
            'python3 -m tools.cgmencode.run_pattern_experiments rolling-isf',
            'python3 -m tools.cgmencode.experiments_validated validate-override',
        ),
        hypotheses=(
            'ISF extraction quality improves when counterfactual-style validation is favored over observed outcomes.',
            'Per-patient temporal drift features are more trustworthy than pooled cohort estimates for parameter extraction.',
        ),
        success_criteria=(
            'Identify one preferred extraction approach plus one fallback approach.',
            'Cite at least two prior experiments or docs that support the recommendation.',
            'Name a concrete validation run to reproduce or extend next.',
        ),
    ),
    'intervention-scoring': DirectionSpec(
        key='intervention-scoring',
        title='Intervention Scoring and Estimated TIR Uplift',
        default_question=(
            'Given prior forecast, hypo, override, and validation results, rank '
            'candidate intervention types by expected TIR benefit and explain '
            'confidence and downside risk.'
        ),
        search_terms=('tir', 'hypo', 'override', 'forecast', 'confidence', 'risk'),
        candidate_files=(
            'tools/cgmencode/run_validation_report.py',
            'tools/cgmencode/experiments_validated.py',
            'tools/cgmencode/run_pattern_experiments.py',
            'tools/cgmencode/README.md',
            'externals/experiments/mlflow-initial-quick_results.json',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
            'python3 -m tools.cgmencode.experiments_validated validate-override',
            'PYTHONPATH=tools python3 tools/cgmencode/run_validation_report.py',
        ),
        hypotheses=(
            'Interventions supported by both forecast and hypo-aware validation are safer to rank highly.',
            '8f forecast models are currently the better base for near-term intervention scoring than 21f models.',
        ),
        success_criteria=(
            'Produce a ranked list of intervention categories with rationale.',
            'Include one confidence-lowering caveat for each top recommendation.',
            'Reference the latest sweep or validated outputs where available.',
        ),
    ),
    'deconfounding-audit': DirectionSpec(
        key='deconfounding-audit',
        title='Deconfounding and Confidence Audit',
        default_question=(
            'Audit whether controller behavior, user behavior, and physiology are '
            'confounding the inferred intervention benefit, and propose the cleanest '
            'follow-up test.'
        ),
        search_terms=('confound', 'counterfactual', 'composite risk', 'pooled aggregation', 'simpson', 'collider'),
        candidate_files=(
            'tools/cgmencode/QUICK_REFERENCE.md',
            'tools/cgmencode/EXP-2895-2900_AUTORESEARCH_PIPELINE.md',
            'tools/cgmencode/README.md',
            'tools/cgmencode/experiments_validated.py',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.run_pattern_experiments temporal-override',
            'python3 -m tools.cgmencode.run_pattern_experiments leave-patient-out',
            'python3 -m tools.cgmencode.run_pattern_experiments insulin-drift',
        ),
        hypotheses=(
            'Counterfactual validation and per-patient aggregation reduce misleading conclusions from controller-mediated outcomes.',
            'Composite scores hide clinically important orthogonal signals and should be replaced by separate audited factors.',
        ),
        success_criteria=(
            'List the main confounders and the evidence that they matter here.',
            'Recommend one stratification or sensitivity analysis to run next.',
            'State where current recommendation confidence should be reduced.',
        ),
    ),
    'proxy-scoping': DirectionSpec(
        key='proxy-scoping',
        title='Proxy Use-Case and Time-Scale Scoping',
        default_question=(
            'Classify the available diabetes physiology proxies by use case, '
            'deconfounding value, and time scale, and identify which proxies are '
            'best suited for decision support, PK interpretation, and EGP-style flair signals.'
        ),
        search_terms=('hepatic', 'egp', 'tdd', '1800', 'flux', 'throughput', 'balance', 'tir', 'period', 'weekly'),
        candidate_files=(
            'tools/cgmencode/exp_metabolic_441.py',
            'tools/cgmencode/exp_autoresearch_581.py',
            'tools/cgmencode/exp_aid_compensation_2629.py',
            'externals/experiments/exp441_product_flux_hepatic.json',
            'externals/experiments/exp442_tdd_normalization.json',
            'externals/experiments/exp581_score_predicts_future_tir.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'externals/experiments/exp-2629_aid_compensation_cascade.json',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.run_research_reproduction product-flux-hepatic',
            'python3 -m tools.cgmencode.run_research_reproduction tdd-normalization',
            'python3 -m tools.cgmencode.run_research_reproduction settings-adequacy',
        ),
        hypotheses=(
            'Different physiology proxies are useful for different decision-support tasks rather than yielding a single universal best representation.',
            'Short-horizon EGP and compensation signals are better for causal warning flair, while period-wise and weekly decompositions are better for actionable settings work.',
        ),
        success_criteria=(
            'Assign at least three proxies to concrete use cases.',
            'State one preferred time scale or horizon for each proxy family.',
            'Identify where a proxy should be treated as explanatory flair rather than decision-grade evidence.',
        ),
    ),
    'settings-followup': DirectionSpec(
        key='settings-followup',
        title='Settings Follow-Up and Time-of-Day Intervention Planning',
        default_question=(
            'Using the settings adequacy, basal-period decomposition, and correction taxonomy work, '
            'identify the most actionable next settings-focused follow-up and explain which time scales '
            'matter for intervention design.'
        ),
        search_terms=('basal', 'period', 'evening', 'morning', 'correction', 'overcorrection', 'tir', 'settings score'),
        candidate_files=(
            'tools/cgmencode/exp_autoresearch_581.py',
            'externals/experiments/exp581_score_predicts_future_tir.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'externals/experiments/exp584_biweekly_settings_tracking.json',
            'tools/cgmencode/run_validation_report.py',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.run_research_reproduction correction-taxonomy',
            'python3 -m tools.cgmencode.run_research_reproduction biweekly-settings',
            'python3 -m tools.cgmencode.run_research_reproduction settings-adequacy',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
        ),
        hypotheses=(
            'Time-of-day basal decomposition is more actionable for settings changes than a global settings adequacy score.',
            'Correction taxonomy can distinguish where intervention quality is limited by slow correction, failed correction, or overcorrection risk.',
            'Biweekly tracking can separate sustained settings drift from short-lived instability better than monthly summaries alone.',
        ),
        success_criteria=(
            'Name the most actionable settings-focused next experiment or analysis.',
            'State which time scale is best for basal tuning versus correction assessment.',
            'Explain whether the next step is mainly tuning, triage, or safety-focused.',
        ),
    ),
    'safety-vs-explanation': DirectionSpec(
        key='safety-vs-explanation',
        title='Safety Endpoints vs Explanatory Proxy Value',
        default_question=(
            'Classify which proxy families are strongest for safety endpoints versus which are mainly explanatory, '
            'and identify the time scales where each contributes the most.'
        ),
        search_terms=('hypo', 'safety', 'explanatory', 'egp', 'correction', 'basal', 'tir', 'auc', 'specificity'),
        candidate_files=(
            'externals/experiments/exp_322v_validated.json',
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'externals/experiments/exp-2629_aid_compensation_cascade.json',
            'externals/experiments/exp442_tdd_normalization.json',
            'tools/cgmencode/README.md',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
            'python3 -m tools.cgmencode.run_research_reproduction correction-taxonomy',
            'python3 -m tools.cgmencode.autoresearch_agent --direction proxy-scoping',
        ),
        hypotheses=(
            'Validated hypo models are better as decision endpoints than physiology proxies, while physiology proxies are stronger as explanatory and triage features.',
            'Short-horizon recovery and correction proxies contribute more to explanation and safety triage than to direct outcome ranking.',
        ),
        success_criteria=(
            'Separate safety-grade signals from explanatory-only signals.',
            'Name one preferred time scale for safety endpoints and one for explanatory proxies.',
            'State whether each proxy family is best for scoring, triage, tuning, or flair.',
        ),
    ),
    'current-research-position': DirectionSpec(
        key='current-research-position',
        title='Current Diabetes Research Position',
        default_question=(
            'Synthesize the strongest recent memos and backing experiments into one current research position, '
            'covering causal hygiene, proxy use, settings actionability, and safety versus explanation.'
        ),
        search_terms=('deconfounding', 'proxy', 'settings', 'safety', 'explanation', 'hypo', 'basal', 'correction'),
        candidate_files=(
            'externals/experiments/autoresearch/20260627-122947_deconfounding-audit.md',
            'externals/experiments/autoresearch/20260627-135059_proxy-scoping.md',
            'externals/experiments/autoresearch/20260627-140610_settings-followup.md',
            'externals/experiments/autoresearch/20260627-141810_safety-vs-explanation.md',
            'externals/experiments/exp_322v_validated.json',
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'externals/experiments/exp-2629_aid_compensation_cascade.json',
            'externals/experiments/exp443_throughput_balance.json',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.autoresearch_agent --direction settings-followup',
            'python3 -m tools.cgmencode.autoresearch_agent --direction safety-vs-explanation',
            'python3 -m tools.cgmencode.autoresearch_agent --direction proxy-scoping',
        ),
        hypotheses=(
            'The current best research position is not a single winning proxy but a layered stack: validated safety endpoints, settings triage signals, and explanatory physiology proxies.',
            'Causal hygiene and use-case scoping are more important than chasing a universal physiological score.',
        ),
        success_criteria=(
            'Summarize the current research position in one memo.',
            'Name the strongest safety endpoint, the most actionable settings signal, and the most useful explanatory proxy.',
            'State one next research direction that follows from the synthesis.',
        ),
    ),
    'titration-safety-followup': DirectionSpec(
        key='titration-safety-followup',
        title='Staged Titration Safety Follow-Up',
        default_question=(
            'Use the staged titration-plan artifacts plus validated hypo results to decide whether the '
            'new parameter-extraction outputs improve safety-oriented follow-up selection and endpoint framing.'
        ),
        search_terms=('titration', 'review-basal-first', 'lockstep-review', 'hypo', 'safety', 'threshold', 'specificity'),
        candidate_files=(
            'externals/experiments/parameter-models/effective-parameter-extractor_plan.json',
            'externals/experiments/parameter-models/effective-parameter-extractor_guidance.json',
            'externals/experiments/exp_322v_validated.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'tools/cgmencode/parameter_model_bundle.py',
            'tools/cgmencode/README.md',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.build_effective_parameter_extractor',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
            'python3 -m tools.cgmencode.autoresearch_agent --direction settings-followup',
        ),
        hypotheses=(
            'Staged titration-plan artifacts improve capability by turning parameter-extraction outputs into explicit safety-constrained next actions.',
            'Validated hypo remains the strongest endpoint guardrail for deciding whether staged titration suggestions are safe enough to prioritize.',
        ),
        success_criteria=(
            'Quantify the staged titration action mix and review burden.',
            'State whether safety framing improved compared with memo-only autoresearch.',
            'Name the next best safety-oriented follow-up command.',
        ),
    ),
    'settings-extraction-special-handling': DirectionSpec(
        key='settings-extraction-special-handling',
        title='Settings Extraction Special Handling',
        default_question=(
            'Summarize the special handling required for basal, ISF, and carb-ratio extraction, '
            'and explain which parts are already encoded in the tracked parameter-model workflow versus still needing richer artifacts.'
        ),
        search_terms=('basal', 'isf', 'carb', 'carb ratio', 'meal size', 'schedule', 'safety margin', 'titration'),
        candidate_files=(
            'externals/experiments/parameter-models/effective-parameter-extractor_settings_handling.json',
            'externals/experiments/parameter-models/effective-parameter-extractor_plan.json',
            'tools/cgmencode/parameter_model_bundle.py',
            'tools/cgmencode/exp_carb_ratio_extraction_2729.py',
            'tools/cgmencode/exp_dose_dependent_cr_2747.py',
            'docs/60-research/wave13-controller-dynamics-report-2026-04-20.md',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.build_effective_parameter_extractor',
            'python3 -m tools.cgmencode.autoresearch_agent --direction settings-followup',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
        ),
        hypotheses=(
            'ISF, basal, and carb ratio require different extraction targets and should not be promoted with one shared rule.',
            'The current tracked workflow is strongest for ISF and basal, while carb-ratio handling remains provisional if it depends on announced meals.',
        ),
        success_criteria=(
            'Describe the distinct handling rule for basal, ISF, and carb ratio.',
            'State which settings already have tracked bundle support and which still need richer artifacts.',
            'Name the best next command for improving settings extraction coverage.',
        ),
    ),
    'settings-precision-vs-accuracy': DirectionSpec(
        key='settings-precision-vs-accuracy',
        title='Settings Precision vs Accuracy Research Needs',
        default_question=(
            'For basal, ISF, and carb ratio, summarize what research is needed to improve precision versus what research is needed to improve accuracy of recommendations.'
        ),
        search_terms=('precision', 'accuracy', 'basal', 'isf', 'carb ratio', 'controller', 'egp', 'safety wall', 'meal size'),
        candidate_files=(
            'externals/experiments/parameter-models/effective-parameter-extractor_settings_handling.json',
            'docs/60-research/wave11-safety-precision-report-2026-04-20.md',
            'docs/60-research/wave12-multifactor-isolation-report-2026-04-20.md',
            'docs/60-research/wave13-controller-dynamics-report-2026-04-20.md',
            'tools/cgmencode/parameter_model_bundle.py',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.autoresearch_agent --direction settings-extraction-special-handling',
            'python3 -m tools.cgmencode.build_effective_parameter_extractor',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
        ),
        hypotheses=(
            'Basal recommendations are closest to actionable accuracy, while ISF and carb ratio still face larger accuracy limits than precision limits.',
            'For ISF and carb ratio, the next research gains come more from causal and controller-aware framing than from narrower confidence intervals alone.',
        ),
        success_criteria=(
            'State the main precision bottleneck for each setting.',
            'State the main accuracy bottleneck for each setting.',
            'Name the highest-value next research step for each setting.',
        ),
    ),
    'controller-aware-causality': DirectionSpec(
        key='controller-aware-causality',
        title='Controller-Aware Accuracy and Causality',
        default_question=(
            'Synthesize how controller-aware accuracy changes causal interpretation, and organize the best deconfounding features by time scale, flair role, and ability to separate controller action from disease course.'
        ),
        search_terms=('controller', 'causal', 'counterfactual', 'time scale', 'flair', 'deconfound', 'basal', 'isf', 'correction', 'throughput'),
        candidate_files=(
            'docs/60-research/wave11-safety-precision-report-2026-04-20.md',
            'docs/60-research/wave12-multifactor-isolation-report-2026-04-20.md',
            'docs/60-research/wave13-controller-dynamics-report-2026-04-20.md',
            'externals/experiments/exp_322v_validated.json',
            'externals/experiments/exp443_throughput_balance.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'externals/experiments/parameter-models/effective-parameter-extractor_settings_handling.json',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.autoresearch_agent --direction deconfounding-audit',
            'python3 -m tools.cgmencode.autoresearch_agent --direction settings-precision-vs-accuracy',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
        ),
        hypotheses=(
            'Controller-aware accuracy should be framed as a layered problem: safety endpoints, controller-state separation features, and explanatory physiology flair at different time scales.',
            'Most observational errors come from controller-mediated feedback, so causal confidence improves more from controller-aware decomposition than from adding more pooled features.',
        ),
        success_criteria=(
            'State which time scales are best for endpoint, controller-separation, and explanatory roles.',
            'Separate flair signals from decision-grade signals.',
            'Name the next best causal-improvement experiment or memo direction.',
        ),
    ),
    'controller-state-stratification': DirectionSpec(
        key='controller-state-stratification',
        title='Controller-State Stratification',
        default_question=(
            'Define practical controller-state strata that help separate controller action from disease course, and map which time scales and features support each stratum.'
        ),
        search_terms=('controller', 'correction', 'failed', 'fast return', 'throughput', 'balance', 'basal', 'time-of-day', 'strata'),
        candidate_files=(
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'externals/experiments/exp443_throughput_balance.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'docs/60-research/wave12-multifactor-isolation-report-2026-04-20.md',
            'docs/60-research/wave13-controller-dynamics-report-2026-04-20.md',
            'externals/experiments/parameter-models/effective-parameter-extractor_settings_handling.json',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.autoresearch_agent --direction deconfounding-audit',
            'python3 -m tools.cgmencode.autoresearch_agent --direction controller-aware-causality',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
        ),
        hypotheses=(
            'Controller-state strata built from correction taxonomy, throughput/balance, and time-of-day tuning signals can isolate controller-mediated behavior better than pooled analysis.',
            'The most useful strata are not disease labels but response modes such as failed correction, fast return, suspension-heavy correction, and persistent period mismatch.',
        ),
        success_criteria=(
            'Name at least three controller-state strata.',
            'State which time scale and features support each stratum.',
            'Explain what causal claim each stratum can and cannot support.',
        ),
    ),
    'stratified-deconfounding-audit': DirectionSpec(
        key='stratified-deconfounding-audit',
        title='Stratified Deconfounding Audit',
        default_question=(
            'Apply the causal audit separately to the main controller-response strata and identify which audit, confidence downgrade, and next test should be used in each stratum.'
        ),
        search_terms=('failed correction', 'fast return', 'throughput', 'balance', 'period mismatch', 'controller', 'counterfactual', 'leave-patient-out'),
        candidate_files=(
            'externals/experiments/autoresearch/20260627-152217_controller-state-stratification.md',
            'externals/experiments/exp583_correction_event_taxonomy.json',
            'externals/experiments/exp443_throughput_balance.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
            'docs/60-research/wave12-multifactor-isolation-report-2026-04-20.md',
            'docs/60-research/wave13-controller-dynamics-report-2026-04-20.md',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.autoresearch_agent --direction deconfounding-audit',
            'python3 -m tools.cgmencode.run_pattern_experiments leave-patient-out',
            'python3 -m tools.cgmencode.run_pattern_experiments temporal-override',
        ),
        hypotheses=(
            'Different controller-response strata require different deconfounding audits rather than one shared audit order.',
            'Confidence downgrades should be strongest in failed-correction and fast-return states, weaker in persistent period-mismatch states.',
        ),
        success_criteria=(
            'Map at least three strata to their best audit and confidence action.',
            'State which pooled claim becomes unsafe inside each stratum.',
            'Name the next best stratified follow-up command.',
        ),
    ),
}

COUNTER_CAUSAL_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        'name': 'composite-risk-collapse',
        'match_terms': ('composite risk', 'composite', 'stack *', 'orthogonal'),
        'risk': 'Combining orthogonal signals into one score can hide causal structure and reverse apparent importance.',
        'mitigation': 'Keep signals separate, report them independently, and compare downstream value without composite collapse.',
    },
    {
        'name': 'pooled-aggregation-dominance',
        'match_terms': ('pooled aggregation', 'groupby', 'patient_id', 'simpson'),
        'risk': 'Pooling across prolific patients can create counter-causal cohort effects and Simpson-style reversals.',
        'mitigation': 'Prefer per-patient aggregation and stratified analyses before drawing cohort-level conclusions.',
    },
    {
        'name': 'observed-outcome-collider',
        'match_terms': ('validate vs observed', 'collider', 'counterfactual', 'closed-loop mode'),
        'risk': 'Observed outcomes can be controller-mediated, making apparent benefit or harm counter-causal.',
        'mitigation': 'Use counterfactual or pre-computed causal proxies and stratify on controller lineage or closed-loop state.',
    },
    {
        'name': 'controller-mediated-feedback',
        'match_terms': ('override', 'suspension', 'controller', 'insulin-controlled drift'),
        'risk': 'Controller actions can respond to the same state used for evaluation, creating feedback loops mistaken for causal signal.',
        'mitigation': 'Audit treatment timing, compare against temporal baselines, and run leave-patient-out or sensitivity analyses.',
    },
)

PATTERN_COMMAND_PREFERENCES: dict[str, tuple[str, ...]] = {
    'composite-risk-collapse': ('validate-override', 'validate-hypo', 'leave-patient-out'),
    'pooled-aggregation-dominance': ('leave-patient-out', 'rolling-isf', 'validate-override'),
    'observed-outcome-collider': ('validate-override', 'rolling-isf', 'leave-patient-out'),
    'controller-mediated-feedback': ('temporal-override', 'leave-patient-out', 'insulin-drift'),
}

REASONING_CORRECTION_LIBRARY: dict[str, dict[str, Any]] = {
    'composite-risk-collapse': {
        'misleading_claim': 'A single composite score is sufficient to rank intervention quality or physiology adequacy.',
        'corrected_claim': 'Keep orthogonal signals separate first, then prove that any combined score preserves downstream decision value.',
        'confidence_action': 'downgrade-until-factorized',
        'hypothesis_terms': ('score', 'composite', 'rank', 'intervention'),
    },
    'pooled-aggregation-dominance': {
        'misleading_claim': 'A pooled cohort average can be treated as if it were a patient-level causal effect.',
        'corrected_claim': 'Use per-patient or stratified summaries before trusting the cohort result; pooled effects are descriptive until that check passes.',
        'confidence_action': 'downgrade-until-stratified',
        'hypothesis_terms': ('per-patient', 'pooled', 'cohort', 'parameter extraction'),
    },
    'observed-outcome-collider': {
        'misleading_claim': 'Observed closed-loop outcomes directly identify whether an intervention or setting is beneficial.',
        'corrected_claim': 'Treat observed outcomes as controller-mediated; prefer counterfactual proxies, controller lineage splits, or validated causal surfaces.',
        'confidence_action': 'downgrade-until-counterfactual',
        'hypothesis_terms': ('counterfactual', 'observed', 'benefit', 'validation', 'settings'),
    },
    'controller-mediated-feedback': {
        'misleading_claim': 'Controller actions can be interpreted as independent evidence of physiology or recommendation quality.',
        'corrected_claim': 'Audit treatment timing and sensitivity because controller actions may be responses to the same state being evaluated.',
        'confidence_action': 'downgrade-until-timing-audit',
        'hypothesis_terms': ('controller', 'override', 'feedback', 'drift', 'hypo'),
    },
}


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'autoresearch'


def _read_text_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding='utf-8').splitlines()
    except UnicodeDecodeError:
        return path.read_text(encoding='utf-8', errors='replace').splitlines()


def _collect_evidence(spec: DirectionSpec, max_hits_per_file: int = 4) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    terms = tuple(term.lower() for term in spec.search_terms)
    with _span('retrieve_context', span_type='RETRIEVER', attributes={'direction': spec.key}) as span:
        span.set_inputs({'search_terms': list(spec.search_terms), 'candidate_files': list(spec.candidate_files)})
        for rel_path in spec.candidate_files:
            path = ROOT / rel_path
            if not path.exists():
                continue
            hits = 0
            for line_no, line in enumerate(_read_text_lines(path), start=1):
                lowered = line.lower()
                if any(term in lowered for term in terms):
                    evidence.append({
                        'path': rel_path,
                        'line': line_no,
                        'snippet': line.strip()[:240],
                    })
                    hits += 1
                    if hits >= max_hits_per_file:
                        break
        span.set_outputs({'evidence_count': len(evidence)})
    return evidence


def _load_recent_sweep_summary() -> dict[str, Any] | None:
    if not RECENT_SWEEP.exists():
        return None
    data = json.loads(RECENT_SWEEP.read_text())
    ranked = sorted(
        data.items(),
        key=lambda item: item[1].get('aggregate', {}).get('mean_mae', float('inf')),
    )
    if not ranked:
        return None
    best_key, best_value = ranked[0]
    return {
        'best_key': best_key,
        'best_mean_mae': best_value.get('aggregate', {}).get('mean_mae'),
        'ranking': [
            {
                'key': key,
                'mean_mae': value.get('aggregate', {}).get('mean_mae'),
                'vs_persistence': value.get('aggregate', {}).get('vs_persistence'),
            }
            for key, value in ranked[:6]
        ],
    }


def _load_json_if_exists(rel_path: str) -> dict[str, Any] | None:
    path = ROOT / rel_path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _load_json_path_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _build_proxy_use_case_matrix() -> list[dict[str, Any]]:
    exp2629 = _load_json_if_exists('externals/experiments/exp-2629_aid_compensation_cascade.json') or {}
    exp441 = _load_json_if_exists('externals/experiments/exp441_product_flux_hepatic.json') or {}
    exp442 = _load_json_if_exists('externals/experiments/exp442_tdd_normalization.json') or {}
    exp443 = _load_json_if_exists('externals/experiments/exp443_throughput_balance.json') or {}
    exp581 = _load_json_if_exists('externals/experiments/exp581_score_predicts_future_tir.json') or {}
    exp582 = _load_json_if_exists('externals/experiments/exp582_per-period_basal_decomposition.json') or {}

    matrix = [
        {
            'proxy': 'Hill-style EGP recovery ratio',
            'best_for': 'short-horizon explanatory flair and hypothesis generation around low-glucose recovery',
            'avoid_for': 'high-confidence intervention scoring or direct mechanistic calibration',
            'preferred_time_scale': 'minutes to ~1 hour around low-glucose or correction episodes',
            'deconfounding_value': 'moderate as a falsification check, low as a final decision variable',
            'evidence': {
                'h4_result': exp2629.get('hypotheses', {}).get('H4', {}).get('result'),
                'median_ratio': exp2629.get('pooled', {}).get('hill_ratio_median'),
            },
        },
        {
            'proxy': 'Hepatic-aware supply-demand sum flux',
            'best_for': 'stable physiology decomposition and settings-oriented metabolic accounting',
            'avoid_for': 'assuming throughput product is inherently better across horizons',
            'preferred_time_scale': '2h to 12h windows for aggregate state interpretation',
            'deconfounding_value': 'high for separating supply vs demand, moderate for downstream prediction',
            'evidence': {
                'product_wins_count': exp441.get('aggregate', {}).get('product_wins_count'),
                'sum_wins_count': exp441.get('aggregate', {}).get('sum_wins_count'),
                'hepatic_rescue_count': sum(
                    1 for item in exp441.get('hepatic_rescue', {}).values() if item.get('rescued')
                ) if exp441.get('hepatic_rescue') else None,
            },
        },
        {
            'proxy': 'TDD normalization / 1800-rule ISF proxy',
            'best_for': 'population priors, initialization, and cross-patient scaling',
            'avoid_for': 'final individualized PK or ISF inference',
            'preferred_time_scale': 'daily to multi-day normalization context',
            'deconfounding_value': 'moderate for population scaling, low for patient-specific causal claims',
            'evidence': {
                'isf_correlation': exp442.get('aggregate', {}).get('isf_agreement', {}).get('correlation'),
                'tdd_mean': exp442.get('aggregate', {}).get('tdd_population', {}).get('mean'),
            },
        },
        {
            'proxy': 'Throughput + balance dual-channel view',
            'best_for': 'medium-horizon event discrimination and multi-scale state separation',
            'avoid_for': 'single-feature mechanistic interpretation in isolation',
            'preferred_time_scale': '6h to 12h windows, where combined separation improves',
            'deconfounding_value': 'moderate because it separates activity intensity from directionality',
            'evidence': {
                'sil_2h': exp443.get('aggregate', {}).get('2h', {}).get('mean_sil_2d'),
                'sil_6h': exp443.get('aggregate', {}).get('6h', {}).get('mean_sil_2d'),
                'sil_12h': exp443.get('aggregate', {}).get('12h', {}).get('mean_sil_2d'),
            },
        },
        {
            'proxy': 'Settings adequacy composite score',
            'best_for': 'broad monthly monitoring and anomaly triage',
            'avoid_for': 'direct prediction of future TIR change without decomposition',
            'preferred_time_scale': 'multi-week to monthly review',
            'deconfounding_value': 'low unless unpacked into constituent factors',
            'evidence': {
                'mean_r_score_tir_change': exp581.get('mean_r'),
            },
        },
        {
            'proxy': 'Per-period basal decomposition',
            'best_for': 'actionable basal tuning and time-of-day decision support',
            'avoid_for': 'single-score ranking across all therapeutic domains',
            'preferred_time_scale': 'circadian / time-of-day windows',
            'deconfounding_value': 'high because it localizes effects by period instead of pooling',
            'evidence': {
                'mean_adjustments': exp582.get('mean_adjustments'),
                'worst_period_counts': exp582.get('worst_period_counts'),
            },
        },
    ]
    return matrix


def _build_current_research_position() -> list[dict[str, Any]]:
    exp2629 = _load_json_if_exists('externals/experiments/exp-2629_aid_compensation_cascade.json') or {}
    exp322 = _load_json_if_exists('externals/experiments/exp_322v_validated.json') or {}
    exp582 = _load_json_if_exists('externals/experiments/exp582_per-period_basal_decomposition.json') or {}
    exp583 = _load_json_if_exists('externals/experiments/exp583_correction_event_taxonomy.json') or {}
    exp443 = _load_json_if_exists('externals/experiments/exp443_throughput_balance.json') or {}

    return [
        {
            'theme': 'Causal hygiene comes first',
            'position': 'Use counterfactual proxies, per-patient aggregation, and leave-patient-out checks before trusting intervention conclusions.',
            'backing': ['20260627-122947_deconfounding-audit.md', 'EXP-310', 'EXP-311'],
        },
        {
            'theme': 'Safety endpoints beat physiology proxies for final decisions',
            'position': 'Validated hypo detection is the strongest decision-grade safety surface, while physiology proxies mainly support explanation and triage.',
            'backing': [
                f"EXP-322v auc_roc≈{exp322.get('multi_seed', {}).get('aggregate', {}).get('auc_roc', {}).get('mean', 'n/a')}",
                '20260627-141810_safety-vs-explanation.md',
            ],
        },
        {
            'theme': 'Time-of-day settings decomposition is actionable',
            'position': 'Per-period basal decomposition and correction taxonomy give more actionable intervention guidance than a single global settings score.',
            'backing': [
                f"EXP-582 mean_adjustments={exp582.get('mean_adjustments', 'n/a')}",
                f"EXP-583 mean_failed={exp583.get('mean_failed', 'n/a')}",
                '20260627-140610_settings-followup.md',
            ],
        },
        {
            'theme': 'Physiology proxies need scope, not a winner-take-all ranking',
            'position': 'Hill-style EGP recovery is best treated as short-horizon explanatory flair, while throughput+balance helps more at 6h–12h and TDD normalization works as a population prior.',
            'backing': [
                f"EXP-2629 H4={exp2629.get('hypotheses', {}).get('H4', {}).get('result', 'n/a')}",
                f"EXP-443 sil_12h={exp443.get('aggregate', {}).get('12h', {}).get('mean_sil_2d', 'n/a')}",
                '20260627-135059_proxy-scoping.md',
            ],
        },
    ]


def _build_titration_safety_summary() -> dict[str, Any]:
    titration_plan = _load_json_if_exists(
        'externals/experiments/parameter-models/effective-parameter-extractor_plan.json'
    ) or {}
    titration_guidance = _load_json_if_exists(
        'externals/experiments/parameter-models/effective-parameter-extractor_guidance.json'
    ) or {}
    exp322 = _load_json_if_exists('externals/experiments/exp_322v_validated.json') or {}

    per_patient = titration_plan.get('per_patient', {})
    staged_counts: dict[str, int] = {}
    review_required = 0
    suggested_steps: list[float] = []
    for patient in per_patient.values():
        action = patient.get('staged_action', 'unknown')
        staged_counts[action] = staged_counts.get(action, 0) + 1
        if patient.get('review_required'):
            review_required += 1
        step = patient.get('suggested_basal_step_pct')
        if step is not None:
            try:
                suggested_steps.append(float(step))
            except (TypeError, ValueError):
                pass

    n_patients = len(per_patient)
    aggregate = exp322.get('multi_seed', {}).get('aggregate', {})
    return {
        'promotion_recommendation': titration_plan.get('promotion_recommendation'),
        'max_basal_step_pct': titration_guidance.get('max_basal_step_pct'),
        'reassessment_days': titration_guidance.get('reassessment_days'),
        'concurrent_change_review_required': titration_guidance.get('concurrent_change_review_required'),
        'n_patients': n_patients,
        'staged_action_counts': staged_counts,
        'review_required_fraction': round(review_required / n_patients, 3) if n_patients else None,
        'mean_suggested_basal_step_pct': (
            round(sum(suggested_steps) / len(suggested_steps), 2) if suggested_steps else None
        ),
        'validated_hypo_guardrail': {
            'auc_roc_mean': aggregate.get('auc_roc', {}).get('mean'),
            'specificity_mean': aggregate.get('specificity', {}).get('mean'),
            'f1_positive_mean': aggregate.get('f1_positive', {}).get('mean'),
        },
        'capability_gain': (
            'Parameter extraction now yields staged, safety-constrained next actions that can be audited against a validated hypo endpoint.'
            if per_patient and aggregate
            else 'Capability gain not yet measurable because staged titration artifacts or validated hypo outputs are missing.'
        ),
    }


def _build_settings_extraction_summary() -> dict[str, Any]:
    settings_handling = _load_json_if_exists(
        'externals/experiments/parameter-models/effective-parameter-extractor_settings_handling.json'
    ) or {}
    bundle = _load_json_if_exists(
        'externals/experiments/parameter-models/effective-parameter-extractor_bundle.json'
    ) or {}

    summary_settings = settings_handling.get('settings', {})
    upstream = bundle.get('upstream_artifacts', {})
    carb_ratio_dependency = summary_settings.get('carb_ratio', {}).get('evidence_loaded', {}).get('depends_on_announced_meals')
    carb_ratio_promotion_ready = summary_settings.get('carb_ratio', {}).get('promotion_ready_without_meals')
    coverage = {
        key: value.get('coverage_fraction')
        for key, value in summary_settings.items()
        if isinstance(value, dict)
    }
    tracked_support = {
        'isf': bool(upstream.get('isf_schedule_optimizer')),
        'basal': bool(upstream.get('basal_schedule_optimizer') or upstream.get('basal_decomposition')),
        'carb_ratio': bool(upstream.get('carb_ratio_analysis') or upstream.get('dose_dependent_cr')) and not carb_ratio_dependency,
    }
    return {
        'tracked_support': tracked_support,
        'coverage_fraction': coverage,
        'announced_meal_dependency': {
            'carb_ratio': carb_ratio_dependency,
            'promotion_ready_without_meals': carb_ratio_promotion_ready,
        },
        'combined_cautions': settings_handling.get('combined_cautions', []),
        'capability_gap': (
            'Carb-ratio handling is not yet promotion-ready because the current CR artifacts still depend on announced meal data.'
            if not tracked_support['carb_ratio']
            else 'All three settings families have tracked artifact support, but carb-ratio promotion still requires careful meal-size review.'
        ),
    }


def _build_settings_precision_accuracy_summary() -> dict[str, Any]:
    settings_handling = _load_json_if_exists(
        'externals/experiments/parameter-models/effective-parameter-extractor_settings_handling.json'
    ) or {}
    exp322 = _load_json_if_exists('externals/experiments/exp_322v_validated.json') or {}

    hypo_guardrail = exp322.get('multi_seed', {}).get('aggregate', {})
    return {
        'basal': {
            'current_state': 'Best current candidate for actionable tuning because personalized EGP and period-wise decomposition greatly improved calibration.',
            'precision_research_needed': [
                'Stabilize per-period drift estimates over biweekly windows and repeated fasting segments.',
                'Improve residual-noise handling so dawn-period and circadian recommendations have tighter uncertainty.',
            ],
            'accuracy_research_needed': [
                'Validate that personalized EGP and period-wise basal changes improve downstream safety endpoints, not just calibration scores.',
                'Separate controller-driven temporary basal behavior from persistent underlying basal need.',
            ],
            'highest_value_next_step': 'Tie period-wise basal recommendations to validated hypo and other held-out safety outcomes after capped staged titration.',
        },
        'isf': {
            'current_state': 'Reasonably predictive when using correction-denominator framing, but direct “true ISF” recovery is accuracy-limited by controller safety margin and indication bias.',
            'precision_research_needed': [
                'Increase qualifying-event coverage with better event selection and more stable denominator rules.',
                'Use leave-patient-out or hierarchical pooling to reduce variance without collapsing to biased regression estimates.',
            ],
            'accuracy_research_needed': [
                'Model controller feedback explicitly or use counterfactual/controller-safe targets instead of raw observational recovery.',
                'Distinguish controller operating ISF from physiological ISF rather than forcing one recommendation to serve both roles.',
            ],
            'highest_value_next_step': 'Build controller-aware or counterfactual ISF targets and evaluate bounded recommendation rules against validated safety endpoints.',
        },
        'carb_ratio': {
            'current_state': 'Precision can improve after multi-factor subtraction, but accuracy and promotion-readiness remain weak because current CR evidence still depends on meal-announcement artifacts.',
            'precision_research_needed': [
                'Find meal-independent carb-impact proxies that cluster repeated meal-like excursions without relying on logged carbs.',
                'Quantify meal-size or absorption-regime effects with latent-meal/UAM-style cohorts rather than announced-meal cohorts.',
            ],
            'accuracy_research_needed': [
                'Replace announced-meal dependence with unannounced or weakly supervised meal detection so CR recommendations reflect realistic workflow data.',
                'Separate controller-added meal insulin from underlying carb sensitivity before promoting any CR setting changes.',
            ],
            'highest_value_next_step': 'Develop a meal-independent carb-impact extraction path and compare its recommendations against safety and trajectory outcomes before treating CR as promotion-ready.',
        },
        'shared_guardrail': {
            'validated_hypo_auc_roc_mean': hypo_guardrail.get('auc_roc', {}).get('mean'),
            'validated_hypo_specificity_mean': hypo_guardrail.get('specificity', {}).get('mean'),
            'principle': 'Precision work narrows uncertainty, but accuracy work must be judged against controller-aware causal framing and validated safety endpoints.',
        },
    }


def _build_controller_causality_summary() -> dict[str, Any]:
    exp322 = _load_json_if_exists('externals/experiments/exp_322v_validated.json') or {}
    exp443 = _load_json_if_exists('externals/experiments/exp443_throughput_balance.json') or {}
    exp582 = _load_json_if_exists('externals/experiments/exp582_per-period_basal_decomposition.json') or {}
    exp583 = _load_json_if_exists('externals/experiments/exp583_correction_event_taxonomy.json') or {}

    hypo = exp322.get('multi_seed', {}).get('aggregate', {})
    return {
        'controller_causal_position': (
            'Observed treatment outcomes are controller-mediated. Recommendation quality should be judged first against validated safety endpoints, '
            'then against controller-separation features, and only then against physiology flair or descriptive proxies.'
        ),
        'time_scales': [
            {
                'scale': 'minutes to ~1 hour',
                'best_for': 'explanatory flair and rapid controller-response interpretation',
                'signals': ['Hill-style EGP recovery ratio', 'correction event taxonomy'],
                'causal_role': 'good for warning flavor and local audit, weak as final decision surface',
            },
            {
                'scale': '2h to 12h',
                'best_for': 'controller-action separation and event discrimination',
                'signals': ['throughput + balance dual-channel view', 'correction-only denominator framing'],
                'causal_role': 'best current middle layer for separating controller work from disease-course interpretation',
                'evidence': {
                    'sil_2h': exp443.get('aggregate', {}).get('2h', {}).get('mean_sil_2d'),
                    'sil_6h': exp443.get('aggregate', {}).get('6h', {}).get('mean_sil_2d'),
                    'sil_12h': exp443.get('aggregate', {}).get('12h', {}).get('mean_sil_2d'),
                },
            },
            {
                'scale': 'circadian / time-of-day',
                'best_for': 'settings tuning and slow controller-state decomposition',
                'signals': ['per-period basal decomposition', 'time-of-day drift residuals'],
                'causal_role': 'most actionable layer for basal tuning once fast controller effects are separated',
                'evidence': {
                    'mean_adjustments': exp582.get('mean_adjustments'),
                    'worst_period_counts': exp582.get('worst_period_counts'),
                },
            },
            {
                'scale': 'biweekly to monthly',
                'best_for': 'stability monitoring and low-frequency drift',
                'signals': ['settings adequacy score', 'biweekly settings tracking'],
                'causal_role': 'useful for triage and persistence, but too pooled for direct causal assignment',
            },
        ],
        'decision_layers': {
            'decision_grade': {
                'signals': ['validated hypo endpoint'],
                'why': 'strongest direct safety guardrail for whether any recommendation framing is acceptable',
                'evidence': {
                    'auc_roc_mean': hypo.get('auc_roc', {}).get('mean'),
                    'specificity_mean': hypo.get('specificity', {}).get('mean'),
                },
            },
            'controller_separation': {
                'signals': ['correction-only denominator ISF', 'throughput + balance', 'correction taxonomy'],
                'why': 'best available signals for distinguishing controller contribution from the underlying physiological course',
                'evidence': {
                    'mean_failed_corrections': exp583.get('mean_failed'),
                    'mean_overcorrection_rate': exp583.get('mean_overcorrection'),
                },
            },
            'flair': {
                'signals': ['EGP recovery ratio', 'global settings adequacy score'],
                'why': 'useful to explain phenomena and generate hypotheses, but not to close the causal loop alone',
            },
        },
        'causal_implications': [
            'Controller-mediated feedback is the dominant observational confound across ISF, basal, and CR.',
            'Removing the controller safety margin can improve apparent physiological accuracy while making real recommendations less safe.',
            'Controller-aware accuracy means the target is not the raw physiological quantity alone, but the quantity that remains useful after the controller has already acted.',
        ],
        'highest_value_next_step': (
            'Extend the deconfounding audit with explicit controller-state strata or replay-style counterfactual comparison, then score resulting recommendation rules against validated hypo outcomes.'
        ),
    }


def _build_controller_state_stratification_summary() -> dict[str, Any]:
    exp443 = _load_json_if_exists('externals/experiments/exp443_throughput_balance.json') or {}
    exp582 = _load_json_if_exists('externals/experiments/exp582_per-period_basal_decomposition.json') or {}
    exp583 = _load_json_if_exists('externals/experiments/exp583_correction_event_taxonomy.json') or {}

    return {
        'strata': [
            {
                'name': 'failed-correction state',
                'time_scale': 'minutes to 2h',
                'supporting_features': ['correction taxonomy failed_pct', 'throughput low / balance high', 'validated hypo guardrail'],
                'what_it_supports': 'Identifying corrections where controller/user action was insufficient and recommendation confidence should be reduced or redirected.',
                'what_it_cannot_support': 'Direct inference about underlying physiological sensitivity without separating controller follow-up actions.',
                'evidence': {
                    'mean_failed_pct': exp583.get('mean_failed'),
                },
            },
            {
                'name': 'fast-return controller-dominant state',
                'time_scale': 'minutes to ~1h',
                'supporting_features': ['correction taxonomy fast_return_pct', 'rapid throughput spikes', 'EGP-style flair'],
                'what_it_supports': 'Auditing whether rapid return windows are driven by aggressive controller response versus slower disease-course drift.',
                'what_it_cannot_support': 'Long-horizon basal or carb-ratio recommendations by itself.',
                'evidence': {
                    'mean_fast_return_pct': exp583.get('mean_fast_return'),
                },
            },
            {
                'name': 'controller-separable correction state',
                'time_scale': '2h to 12h',
                'supporting_features': ['throughput + balance', 'correction-only denominator framing', 'class separation windows'],
                'what_it_supports': 'Separating controller work from background course when comparing correction episodes against meal or stable windows.',
                'what_it_cannot_support': 'Proof of causal physiology if the controller policy itself changes across cohorts.',
                'evidence': {
                    'sil_2h': exp443.get('aggregate', {}).get('2h', {}).get('mean_sil_2d'),
                    'sil_6h': exp443.get('aggregate', {}).get('6h', {}).get('mean_sil_2d'),
                    'sil_12h': exp443.get('aggregate', {}).get('12h', {}).get('mean_sil_2d'),
                },
            },
            {
                'name': 'persistent period-mismatch state',
                'time_scale': 'circadian / time-of-day',
                'supporting_features': ['per-period basal decomposition', 'repeated fasting drift residuals', 'worst period counts'],
                'what_it_supports': 'Linking recurrent mismatch to slower controller-state or basal-setting issues rather than one-off events.',
                'what_it_cannot_support': 'Immediate correction-action attribution during single episodes.',
                'evidence': {
                    'mean_adjustments': exp582.get('mean_adjustments'),
                    'worst_period_counts': exp582.get('worst_period_counts'),
                },
            },
        ],
        'stratification_principle': (
            'Prefer response-mode strata over pooled patient cohorts: stratify by how the controller responded, then ask what disease-course claim remains after that response mode is isolated.'
        ),
        'highest_value_next_step': (
            'Apply the deconfounding audit separately within failed-correction, fast-return, and persistent-period-mismatch strata, then compare whether recommendation rules keep their safety profile under validated hypo scoring.'
        ),
    }


def _build_stratified_deconfounding_summary() -> dict[str, Any]:
    correction_taxonomy = _load_json_if_exists('externals/experiments/exp583_correction_event_taxonomy.json') or {}
    throughput_balance = _load_json_if_exists('externals/experiments/exp443_throughput_balance.json') or {}
    basal_decomp = _load_json_if_exists('externals/experiments/exp582_per-period_basal_decomposition.json') or {}

    return {
        'strata_audits': [
            {
                'stratum': 'failed-correction state',
                'unsafe_pooled_claim': 'Observed poor response directly reveals underlying physiological resistance.',
                'best_audit': 'leave-patient-out plus controller-lineage sensitivity audit',
                'confidence_action': 'downgrade strongly until controller follow-up actions are separated',
                'next_test': 'python3 -m tools.cgmencode.run_pattern_experiments leave-patient-out',
                'evidence': {
                    'mean_failed_pct': correction_taxonomy.get('mean_failed'),
                },
            },
            {
                'stratum': 'fast-return controller-dominant state',
                'unsafe_pooled_claim': 'Rapid resolution windows represent clean physiological success rather than aggressive controller intervention.',
                'best_audit': 'temporal-override comparison with timing audit',
                'confidence_action': 'downgrade until event timing shows the controller is not the main actor',
                'next_test': 'python3 -m tools.cgmencode.run_pattern_experiments temporal-override',
                'evidence': {
                    'mean_fast_return_pct': correction_taxonomy.get('mean_fast_return'),
                },
            },
            {
                'stratum': 'controller-separable correction state',
                'unsafe_pooled_claim': 'All correction windows can share one common causal interpretation.',
                'best_audit': 'throughput/balance class-separation review plus leave-patient-out generalization',
                'confidence_action': 'downgrade moderately when separation collapses across patients or horizons',
                'next_test': 'python3 -m tools.cgmencode.run_pattern_experiments leave-patient-out',
                'evidence': {
                    'sil_2h': throughput_balance.get('aggregate', {}).get('2h', {}).get('mean_sil_2d'),
                    'sil_6h': throughput_balance.get('aggregate', {}).get('6h', {}).get('mean_sil_2d'),
                    'sil_12h': throughput_balance.get('aggregate', {}).get('12h', {}).get('mean_sil_2d'),
                },
            },
            {
                'stratum': 'persistent period-mismatch state',
                'unsafe_pooled_claim': 'Repeated basal mismatch can be interpreted from single correction episodes.',
                'best_audit': 'period-wise residual review with slower-horizon stratification',
                'confidence_action': 'downgrade only for fast claims; keep moderate confidence for slow tuning claims',
                'next_test': 'python3 -m tools.cgmencode.autoresearch_agent --direction settings-followup',
                'evidence': {
                    'mean_adjustments': basal_decomp.get('mean_adjustments'),
                    'worst_period_counts': basal_decomp.get('worst_period_counts'),
                },
            },
        ],
        'shared_principle': (
            'Run the deconfounding audit inside the response mode where the claim is made. Pooled causal confidence should not survive if it fails within the dominant controller-response strata.'
        ),
        'highest_value_next_step': (
            'Start with failed-correction and fast-return strata, because those modes are most likely to overstate physiological certainty when controller timing is ignored.'
        ),
    }


def _counter_causal_audit(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pattern in COUNTER_CAUSAL_PATTERNS:
        matched_on: list[str] = []
        examples: list[str] = []
        for item in evidence:
            text = item['snippet'].lower()
            if any(term in text for term in pattern['match_terms']):
                matched_on.extend([term for term in pattern['match_terms'] if term in text])
                examples.append(f"{item['path']}:{item['line']}")
        if matched_on:
            findings.append({
                'pattern': pattern['name'],
                'matched_terms': sorted(set(matched_on)),
                'risk': pattern['risk'],
                'mitigation': pattern['mitigation'],
                'evidence_refs': examples[:4],
            })
    return findings


def _prioritize_command(
    recommended_commands: list[str],
    counter_causal_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not recommended_commands:
        return None

    scores = {cmd: 0 for cmd in recommended_commands}
    reasons: dict[str, list[str]] = {cmd: [] for cmd in recommended_commands}

    for finding in counter_causal_findings:
        for preferred in PATTERN_COMMAND_PREFERENCES.get(finding['pattern'], ()):
            for cmd in recommended_commands:
                if preferred in cmd:
                    scores[cmd] += 1
                    reasons[cmd].append(
                        f"{finding['pattern']} -> prefer `{preferred}` to mitigate {finding['risk'].lower()}"
                    )

    best_cmd = max(recommended_commands, key=lambda cmd: (scores[cmd], -recommended_commands.index(cmd)))
    if scores[best_cmd] == 0:
        return {
            'command': recommended_commands[0],
            'reason': 'No counter-causal redirect triggered. Keep the first recommended command as the default next step.',
            'score': 0,
        }
    return {
        'command': best_cmd,
        'reason': '; '.join(reasons[best_cmd]),
        'score': scores[best_cmd],
    }


def _matching_hypotheses(
    pattern_name: str,
    hypotheses: list[str],
) -> list[str]:
    template = REASONING_CORRECTION_LIBRARY.get(pattern_name, {})
    terms = tuple(str(term).lower() for term in template.get('hypothesis_terms', ()))
    if terms:
        matched = [
            hypothesis for hypothesis in hypotheses
            if any(term in hypothesis.lower() for term in terms)
        ]
        if matched:
            return matched[:2]
    return hypotheses[:1]


def _build_reasoning_corrections(
    hypotheses: list[str],
    counter_causal_findings: list[dict[str, Any]],
    prioritized_follow_up: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    corrections: list[dict[str, Any]] = []
    for finding in counter_causal_findings:
        template = REASONING_CORRECTION_LIBRARY.get(finding['pattern'], {})
        corrections.append({
            'pattern': finding['pattern'],
            'misleading_claim': template.get(
                'misleading_claim',
                f"Treat the {finding['pattern']} signal as decision-grade without additional audit.",
            ),
            'corrected_claim': template.get('corrected_claim', finding['mitigation']),
            'confidence_action': template.get('confidence_action', 'downgrade-until-reviewed'),
            'affected_hypotheses': _matching_hypotheses(finding['pattern'], hypotheses),
            'replacement_test': prioritized_follow_up.get('command') if prioritized_follow_up else None,
            'evidence_refs': finding.get('evidence_refs', []),
            'mitigation': finding['mitigation'],
        })
    return corrections


def build_research_plan(direction: str, question: str | None = None) -> dict[str, Any]:
    if direction not in DIRECTIONS:
        raise KeyError(f'Unknown direction: {direction}')
    spec = DIRECTIONS[direction]
    prompt = question or spec.default_question

    with _span('plan', span_type='CHAIN', attributes={'direction': direction}) as span:
        span.set_inputs({'question': prompt})
        evidence = _collect_evidence(spec)
        plan: dict[str, Any] = {
            'direction': spec.key,
            'title': spec.title,
            'question': prompt,
            'evidence': evidence,
            'hypotheses': list(spec.hypotheses),
            'recommended_commands': list(spec.recommended_commands),
            'success_criteria': list(spec.success_criteria),
            'next_steps': [
                'Review the cited evidence snippets and decide whether to reproduce an existing run or launch a new follow-up.',
                'Run the top recommended command if the evidence supports it.',
                'Record confidence, contradictions, and remaining data gaps after the run.',
            ],
        }
        plan['counter_causal_findings'] = _counter_causal_audit(evidence)
        plan['prioritized_follow_up'] = _prioritize_command(
            plan['recommended_commands'],
            plan['counter_causal_findings'],
        )
        plan['reasoning_corrections'] = _build_reasoning_corrections(
            plan['hypotheses'],
            plan['counter_causal_findings'],
            plan['prioritized_follow_up'],
        )
        if spec.key == 'intervention-scoring':
            sweep = _load_recent_sweep_summary()
            if sweep:
                plan['recent_sweep'] = sweep
        if spec.key == 'proxy-scoping':
            plan['proxy_use_case_matrix'] = _build_proxy_use_case_matrix()
        if spec.key == 'current-research-position':
            plan['current_research_position'] = _build_current_research_position()
        if spec.key == 'titration-safety-followup':
            plan['titration_safety_summary'] = _build_titration_safety_summary()
        if spec.key == 'settings-extraction-special-handling':
            plan['settings_extraction_summary'] = _build_settings_extraction_summary()
        if spec.key == 'settings-precision-vs-accuracy':
            plan['settings_precision_accuracy_summary'] = _build_settings_precision_accuracy_summary()
        if spec.key == 'controller-aware-causality':
            plan['controller_causality_summary'] = _build_controller_causality_summary()
        if spec.key == 'controller-state-stratification':
            plan['controller_state_stratification_summary'] = _build_controller_state_stratification_summary()
        if spec.key == 'stratified-deconfounding-audit':
            plan['stratified_deconfounding_summary'] = _build_stratified_deconfounding_summary()
        span.set_outputs({
            'evidence_count': len(evidence),
            'command_count': len(spec.recommended_commands),
            'counter_causal_count': len(plan['counter_causal_findings']),
            'has_prioritized_follow_up': int(plan['prioritized_follow_up'] is not None),
        })
    return plan


def _write_outputs(plan: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d-%H%M%S')}_{_slug(plan['direction'])}"
    json_path = output_dir / f'{stem}.json'
    md_path = output_dir / f'{stem}.md'

    json_path.write_text(json.dumps(plan, indent=2, default=str), encoding='utf-8')

    lines = [
        f"# {plan['title']}",
        '',
        f"**Direction**: `{plan['direction']}`",
        '',
        '## Research Question',
        '',
        plan['question'],
        '',
        '## Evidence',
        '',
    ]
    for item in plan['evidence']:
        lines.append(f"- `{item['path']}:{item['line']}` — {item['snippet']}")
    lines.extend(['', '## Hypotheses', ''])
    lines.extend([f'- {item}' for item in plan['hypotheses']])
    lines.extend(['', '## Recommended Commands', ''])
    lines.extend([f'- `{cmd}`' for cmd in plan['recommended_commands']])
    if plan.get('prioritized_follow_up'):
        lines.extend(['', '## Prioritized Follow-Up', ''])
        lines.append(f"- command: `{plan['prioritized_follow_up']['command']}`")
        lines.append(f"- rationale: {plan['prioritized_follow_up']['reason']}")
    if plan.get('counter_causal_findings'):
        lines.extend(['', '## Counter-Causal Audit', ''])
        for finding in plan['counter_causal_findings']:
            lines.append(f"- **{finding['pattern']}**: {finding['risk']}")
            lines.append(f"  - mitigation: {finding['mitigation']}")
            lines.append(f"  - evidence: {', '.join(finding['evidence_refs'])}")
    if plan.get('reasoning_corrections'):
        lines.extend(['', '## Corrected Reasoning', ''])
        for correction in plan['reasoning_corrections']:
            lines.append(f"- **{correction['pattern']}**")
            lines.append(f"  - misleading claim: {correction['misleading_claim']}")
            lines.append(f"  - corrected claim: {correction['corrected_claim']}")
            lines.append(f"  - confidence action: {correction['confidence_action']}")
            if correction.get('replacement_test'):
                lines.append(f"  - replacement test: `{correction['replacement_test']}`")
            if correction.get('affected_hypotheses'):
                lines.append(f"  - affected hypotheses: {'; '.join(correction['affected_hypotheses'])}")
            lines.append(f"  - evidence: {', '.join(correction['evidence_refs'])}")
    if 'recent_sweep' in plan:
        lines.extend(['', '## Recent Sweep Summary', ''])
        lines.append(f"- Best config: `{plan['recent_sweep']['best_key']}`")
        lines.extend([
            f"- `{row['key']}`: MAE={row['mean_mae']}, vs persistence={row['vs_persistence']}"
            for row in plan['recent_sweep']['ranking']
        ])
    if plan.get('proxy_use_case_matrix'):
        lines.extend(['', '## Proxy Use-Case Matrix', ''])
        for row in plan['proxy_use_case_matrix']:
            lines.append(f"- **{row['proxy']}**")
            lines.append(f"  - best for: {row['best_for']}")
            lines.append(f"  - avoid for: {row['avoid_for']}")
            lines.append(f"  - preferred time scale: {row['preferred_time_scale']}")
            lines.append(f"  - deconfounding value: {row['deconfounding_value']}")
            lines.append(f"  - evidence: {json.dumps(row['evidence'], default=str, sort_keys=True)}")
    if plan.get('current_research_position'):
        lines.extend(['', '## Current Research Position', ''])
        for row in plan['current_research_position']:
            lines.append(f"- **{row['theme']}**: {row['position']}")
            lines.append(f"  - backing: {', '.join(row['backing'])}")
    if plan.get('titration_safety_summary'):
        summary = plan['titration_safety_summary']
        lines.extend(['', '## Titration Safety Summary', ''])
        lines.append(f"- promotion recommendation: {summary.get('promotion_recommendation')}")
        lines.append(f"- max basal step pct: {summary.get('max_basal_step_pct')}")
        lines.append(f"- reassessment days: {summary.get('reassessment_days')}")
        lines.append(f"- review required fraction: {summary.get('review_required_fraction')}")
        lines.append(f"- staged action counts: {json.dumps(summary.get('staged_action_counts', {}), sort_keys=True)}")
        lines.append(f"- validated hypo guardrail: {json.dumps(summary.get('validated_hypo_guardrail', {}), sort_keys=True)}")
        lines.append(f"- capability gain: {summary.get('capability_gain')}")
    if plan.get('settings_extraction_summary'):
        summary = plan['settings_extraction_summary']
        lines.extend(['', '## Settings Extraction Summary', ''])
        lines.append(f"- tracked support: {json.dumps(summary.get('tracked_support', {}), sort_keys=True)}")
        lines.append(f"- coverage fraction: {json.dumps(summary.get('coverage_fraction', {}), sort_keys=True)}")
        lines.append(f"- announced meal dependency: {json.dumps(summary.get('announced_meal_dependency', {}), sort_keys=True)}")
        lines.append(f"- capability gap: {summary.get('capability_gap')}")
        for caution in summary.get('combined_cautions', []):
            lines.append(f"- caution: {caution}")
    if plan.get('settings_precision_accuracy_summary'):
        summary = plan['settings_precision_accuracy_summary']
        lines.extend(['', '## Settings Precision vs Accuracy Summary', ''])
        for key in ('basal', 'isf', 'carb_ratio'):
            row = summary.get(key, {})
            lines.append(f"- **{key}**: {row.get('current_state')}")
            lines.append(f"  - precision research: {'; '.join(row.get('precision_research_needed', []))}")
            lines.append(f"  - accuracy research: {'; '.join(row.get('accuracy_research_needed', []))}")
            lines.append(f"  - next step: {row.get('highest_value_next_step')}")
        if summary.get('shared_guardrail'):
            lines.append(f"- shared guardrail: {json.dumps(summary['shared_guardrail'], sort_keys=True)}")
    if plan.get('controller_causality_summary'):
        summary = plan['controller_causality_summary']
        lines.extend(['', '## Controller-Aware Causality Summary', ''])
        lines.append(f"- position: {summary.get('controller_causal_position')}")
        lines.append(f"- next step: {summary.get('highest_value_next_step')}")
        lines.extend(['', '### Time Scales', ''])
        for row in summary.get('time_scales', []):
            lines.append(f"- **{row.get('scale')}**")
            lines.append(f"  - best for: {row.get('best_for')}")
            lines.append(f"  - signals: {', '.join(row.get('signals', []))}")
            lines.append(f"  - causal role: {row.get('causal_role')}")
            if row.get('evidence'):
                lines.append(f"  - evidence: {json.dumps(row.get('evidence'), sort_keys=True)}")
        lines.extend(['', '### Decision Layers', ''])
        for key, row in summary.get('decision_layers', {}).items():
            lines.append(f"- **{key}**: {row.get('why')}")
            lines.append(f"  - signals: {', '.join(row.get('signals', []))}")
            if row.get('evidence'):
                lines.append(f"  - evidence: {json.dumps(row.get('evidence'), sort_keys=True)}")
        lines.extend(['', '### Causal Implications', ''])
        for item in summary.get('causal_implications', []):
            lines.append(f"- {item}")
    if plan.get('controller_state_stratification_summary'):
        summary = plan['controller_state_stratification_summary']
        lines.extend(['', '## Controller-State Stratification Summary', ''])
        lines.append(f"- principle: {summary.get('stratification_principle')}")
        lines.append(f"- next step: {summary.get('highest_value_next_step')}")
        for row in summary.get('strata', []):
            lines.append(f"- **{row.get('name')}**")
            lines.append(f"  - time scale: {row.get('time_scale')}")
            lines.append(f"  - supporting features: {', '.join(row.get('supporting_features', []))}")
            lines.append(f"  - supports: {row.get('what_it_supports')}")
            lines.append(f"  - cannot support: {row.get('what_it_cannot_support')}")
            if row.get('evidence'):
                lines.append(f"  - evidence: {json.dumps(row.get('evidence'), sort_keys=True)}")
    if plan.get('stratified_deconfounding_summary'):
        summary = plan['stratified_deconfounding_summary']
        lines.extend(['', '## Stratified Deconfounding Summary', ''])
        lines.append(f"- principle: {summary.get('shared_principle')}")
        lines.append(f"- next step: {summary.get('highest_value_next_step')}")
        for row in summary.get('strata_audits', []):
            lines.append(f"- **{row.get('stratum')}**")
            lines.append(f"  - unsafe pooled claim: {row.get('unsafe_pooled_claim')}")
            lines.append(f"  - best audit: {row.get('best_audit')}")
            lines.append(f"  - confidence action: {row.get('confidence_action')}")
            lines.append(f"  - next test: `{row.get('next_test')}`")
            if row.get('evidence'):
                lines.append(f"  - evidence: {json.dumps(row.get('evidence'), sort_keys=True)}")
    lines.extend(['', '## Success Criteria', ''])
    lines.extend([f'- {item}' for item in plan['success_criteria']])
    lines.extend(['', '## Next Steps', ''])
    lines.extend([f'- {item}' for item in plan['next_steps']])
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return json_path, md_path


def evaluate_research_plan(plan: dict[str, Any]) -> dict[str, Any]:
    evidence = plan.get('evidence', [])
    evidence_refs = {item.get('path') for item in evidence if item.get('path')}
    command_count = len(plan.get('recommended_commands', []))
    hypothesis_count = len(plan.get('hypotheses', []))
    success_criteria_count = len(plan.get('success_criteria', []))
    counter_causal_count = len(plan.get('counter_causal_findings', []))
    reasoning_corrections = plan.get('reasoning_corrections', [])
    correction_count = len(reasoning_corrections)
    prioritized_follow_up = plan.get('prioritized_follow_up')

    evidence_coverage = min(1.0, len(evidence) / max(1, hypothesis_count * 2))
    command_coverage = min(1.0, command_count / max(1, success_criteria_count))
    counter_causal_score = 1.0 if counter_causal_count and prioritized_follow_up else (
        0.5 if counter_causal_count else 0.0
    )
    retrieval_diversity = min(1.0, len(evidence_refs) / max(1, hypothesis_count))
    correction_score = 1.0 if counter_causal_count == 0 else min(
        1.0,
        correction_count / max(1, counter_causal_count),
    )
    readiness_score = round(
        0.4 * evidence_coverage
        + 0.25 * command_coverage
        + 0.2 * retrieval_diversity
        + 0.15 * counter_causal_score,
        3,
    )
    if readiness_score >= 0.75:
        readiness = 'candidate'
    elif readiness_score >= 0.5:
        readiness = 'needs-review'
    else:
        readiness = 'needs-more-evidence'

    return {
        'schema_version': '1.0',
        'review_status': 'unreviewed',
        'evidence_count': len(evidence),
        'evidence_file_count': len(evidence_refs),
        'hypothesis_count': hypothesis_count,
        'recommended_command_count': command_count,
        'success_criteria_count': success_criteria_count,
        'counter_causal_count': counter_causal_count,
        'reasoning_correction_count': correction_count,
        'has_prioritized_follow_up': bool(prioritized_follow_up),
        'evidence_coverage_score': round(evidence_coverage, 3),
        'command_coverage_score': round(command_coverage, 3),
        'retrieval_diversity_score': round(retrieval_diversity, 3),
        'counter_causal_audit_score': round(counter_causal_score, 3),
        'reasoning_correction_score': round(correction_score, 3),
        'readiness_score': readiness_score,
        'readiness': readiness,
    }


def build_model_candidate_from_plan(
    plan: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any] | None:
    direction = plan.get('direction')
    if direction != 'parameter-extraction':
        return None

    evidence_refs = [f"{item['path']}:{item['line']}" for item in plan.get('evidence', [])[:8]]
    prioritized = plan.get('prioritized_follow_up') or {}
    return {
        'candidate_name': 'effective-parameter-extractor',
        'candidate_kind': 'structured-physiology-model',
        'registration_readiness': evaluation['readiness'],
        'status': 'candidate',
        'source': 'autoresearch-genai-pilot',
        'problem_statement': plan.get('question'),
        'intended_use': (
            'Infer effective therapy parameters such as ISF, basal tendencies, and '
            'related correction behavior from retrospective CGM and insulin history.'
        ),
        'simple_ml_research_alignment': {
            'target_research': 'simple-ml-insulin-sensitivity-and-basal-rates',
            'learned_objects': ['isf_schedule', 'basal_schedule', 'carb_ratio_strategy', 'dose_response_fit'],
            'algorithm_shape': [
                'segment selection',
                'digestion gating',
                'least-squares trend fitting',
                'time-of-day schedule updates',
            ],
        },
        'inputs': {
            'required': ['cgm_history', 'insulin_history', 'time_of_day', 'therapy_profile'],
            'optional': ['controller_context', 'meal_annotations', 'override_state'],
        },
        'outputs': {
            'primary': ['effective_isf_estimate', 'basal_adjustment_signal', 'carb_ratio_handling', 'validation_follow_up'],
            'artifacts': ['parameter_schedule_json', 'dose_response_fit_json', 'evaluation_summary_json', 'settings_special_handling_json'],
        },
        'recommended_next_command': prioritized.get('command'),
        'evidence_refs': evidence_refs,
        'supporting_hypotheses': list(plan.get('hypotheses', [])),
        'evaluation_summary': evaluation,
    }


def _build_learned_bundle_for_candidate(
    model_candidate: dict[str, Any] | None,
    output_dir: Path,
) -> tuple[Path | None, Path | None, dict[str, Any] | None, Path | None, Path | None, dict[str, Any] | None, Path | None, dict[str, Any] | None, Path | None, dict[str, Any] | None, Path | None, dict[str, Any] | None]:
    if not model_candidate or not DEFAULT_VALIDATION_RESULTS.exists():
        return None, None, None, None, None, None, None, None, None, None, None, None
    results = json.loads(DEFAULT_VALIDATION_RESULTS.read_text(encoding='utf-8'))
    bundle = build_effective_parameter_bundle(
        results,
        source_path=str(DEFAULT_VALIDATION_RESULTS),
        score_predicts_future_tir=_load_json_path_if_exists(DEFAULT_SCORE_TIR),
        basal_decomposition=_load_json_path_if_exists(DEFAULT_BASAL_DECOMP),
        isf_schedule_optimizer=_load_json_path_if_exists(DEFAULT_ISF_SCHEDULE),
        basal_schedule_optimizer=_load_json_path_if_exists(DEFAULT_BASAL_SCHEDULE),
        carb_ratio_analysis=_load_json_path_if_exists(DEFAULT_CARB_RATIO),
        dose_dependent_cr=_load_json_path_if_exists(DEFAULT_DOSE_DEPENDENT_CR),
    )
    evaluation = evaluate_effective_parameter_bundle(bundle)
    thresholds = propose_effective_parameter_thresholds(evaluation)
    assessment = assess_effective_parameter_thresholds(evaluation, thresholds)
    guidance = derive_titration_guidance(evaluation, assessment)
    plan = derive_titration_plan(bundle, evaluation, assessment, guidance)
    settings_handling = bundle.get('settings_special_handling')
    stem = _slug(model_candidate['candidate_name'])
    bundle_path = save_bundle(bundle, output_dir / f'{stem}_bundle.json')
    evaluation_path = save_bundle(evaluation, output_dir / f'{stem}_bundle_evaluation.json')
    thresholds_path = save_bundle(thresholds, output_dir / f'{stem}_bundle_thresholds.json')
    assessment_path = save_bundle(assessment, output_dir / f'{stem}_bundle_assessment.json')
    guidance_path = save_bundle(guidance, output_dir / f'{stem}_bundle_guidance.json')
    plan_path = save_bundle(plan, output_dir / f'{stem}_bundle_plan.json')
    settings_handling_path = (
        save_bundle(settings_handling, output_dir / f'{stem}_bundle_settings_handling.json')
        if settings_handling else None
    )
    return bundle_path, evaluation_path, evaluation, thresholds_path, assessment_path, assessment, guidance_path, guidance, plan_path, plan, settings_handling_path, settings_handling


def _build_trace_payload(
    plan: dict[str, Any],
    evaluation: dict[str, Any],
    json_path: Path,
    md_path: Path,
    model_candidate: dict[str, Any] | None,
    pyfunc_model_path: Path | None,
    pyfunc_model_uri: str | None,
    bundle_path: Path | None,
    bundle_evaluation_path: Path | None,
    model_evaluation: dict[str, Any] | None,
    thresholds_path: Path | None,
    assessment_path: Path | None,
    threshold_assessment: dict[str, Any] | None,
    guidance_path: Path | None,
    titration_guidance: dict[str, Any] | None,
    plan_path: Path | None,
    titration_plan: dict[str, Any] | None,
    settings_handling_path: Path | None,
    settings_special_handling: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        'schema_version': '1.0',
        'trace_type': 'genai-autoresearch-pilot',
        'direction': plan['direction'],
        'request': {
            'question': plan['question'],
            'hypotheses': plan['hypotheses'],
        },
        'retrieval': {
            'evidence_count': len(plan['evidence']),
            'evidence_refs': [f"{item['path']}:{item['line']}" for item in plan['evidence'][:12]],
        },
        'audit': {
            'counter_causal_findings': plan.get('counter_causal_findings', []),
            'reasoning_corrections': plan.get('reasoning_corrections', []),
            'prioritized_follow_up': plan.get('prioritized_follow_up'),
        },
        'evaluation': evaluation,
        'model_evaluation': model_evaluation,
        'threshold_assessment': threshold_assessment,
        'titration_guidance': titration_guidance,
        'titration_plan': titration_plan,
        'settings_special_handling': settings_special_handling,
        'outputs': {
            'json_artifact': str(json_path),
            'markdown_artifact': str(md_path),
            'recommended_commands': plan['recommended_commands'],
            'model_candidate_name': model_candidate['candidate_name'] if model_candidate else None,
            'pyfunc_model_path': str(pyfunc_model_path) if pyfunc_model_path else None,
            'pyfunc_model_uri': pyfunc_model_uri,
            'bundle_path': str(bundle_path) if bundle_path else None,
            'bundle_evaluation_path': str(bundle_evaluation_path) if bundle_evaluation_path else None,
            'thresholds_path': str(thresholds_path) if thresholds_path else None,
            'assessment_path': str(assessment_path) if assessment_path else None,
            'guidance_path': str(guidance_path) if guidance_path else None,
            'plan_path': str(plan_path) if plan_path else None,
            'settings_handling_path': str(settings_handling_path) if settings_handling_path else None,
        },
    }


def run_direction(direction: str, question: str | None, output_dir: Path) -> dict[str, Any]:
    spec = DIRECTIONS[direction]
    run_context = build_run_context(
        task_type='genai-autoresearch',
        result_type='trace-evaluation',
        artifact_role='genai-trace',
        data_source='workspace-docs-and-results',
        split_strategy='retrieval-over-local-artifacts',
        split_details={'candidate_file_count': len(spec.candidate_files)},
        model_family='autoresearch-pilot',
        experiment_family=direction,
        extra_tags={'surface': 'genai-pilot', 'direction': direction},
        extra_params={'direction': direction},
    )
    with start_run(
        run_name=f'autoresearch-{direction}',
        tags={'runner': 'autoresearch_agent', 'surface': 'genai-pilot', 'direction': direction, **run_context['tags']},
        params={'direction': direction, 'question': question or spec.default_question, **run_context['params']},
    ):
        log_run_context(run_context)
        with _span('autoresearch_request', span_type='AGENT', attributes={'direction': direction}) as span:
            plan = build_research_plan(direction, question=question)
            json_path, md_path = _write_outputs(plan, output_dir)
            evaluation = evaluate_research_plan(plan)
            model_candidate = build_model_candidate_from_plan(plan, evaluation)
            (
                bundle_path,
                bundle_evaluation_path,
                model_evaluation,
                thresholds_path,
                assessment_path,
                threshold_assessment,
                guidance_path,
                titration_guidance,
                plan_path,
                titration_plan,
                settings_handling_path,
                settings_special_handling,
            ) = _build_learned_bundle_for_candidate(
                model_candidate, output_dir
            )
            pyfunc_model_path: Path | None = None
            pyfunc_model_uri: str | None = None
            if model_candidate:
                if bundle_path:
                    model_candidate['bundle_path'] = str(bundle_path)
                if bundle_evaluation_path:
                    model_candidate['bundle_evaluation_path'] = str(bundle_evaluation_path)
                if model_evaluation:
                    model_candidate['bundle_evaluation'] = model_evaluation
                if thresholds_path:
                    model_candidate['thresholds_path'] = str(thresholds_path)
                if assessment_path:
                    model_candidate['threshold_assessment_path'] = str(assessment_path)
                if threshold_assessment:
                    model_candidate['threshold_assessment'] = threshold_assessment
                if guidance_path:
                    model_candidate['guidance_path'] = str(guidance_path)
                if titration_guidance:
                    model_candidate['titration_guidance'] = titration_guidance
                if plan_path:
                    model_candidate['plan_path'] = str(plan_path)
                if titration_plan:
                    model_candidate['titration_plan'] = titration_plan
                if settings_handling_path:
                    model_candidate['settings_handling_path'] = str(settings_handling_path)
                if settings_special_handling:
                    model_candidate['settings_special_handling'] = settings_special_handling
                pyfunc_model_path = output_dir / f'{json_path.stem}_effective_parameter_extractor_model'
                saved_path = save_effective_parameter_extractor_model(pyfunc_model_path, model_candidate)
                if saved_path:
                    pyfunc_model_path = Path(saved_path)
                    artifacts = {'candidate_json': str(pyfunc_model_path.parent / f'{pyfunc_model_path.name}_candidate.json')}
                    if bundle_path:
                        artifacts['bundle_json'] = str(bundle_path)
                    pyfunc_model_uri = log_pyfunc_model(
                        'models/pyfunc/effective_parameter_extractor',
                        python_model=EffectiveParameterExtractorModel(model_candidate),
                        artifacts=artifacts,
                        input_example=build_input_example(),
                    )
            trace_payload = _build_trace_payload(
                plan,
                evaluation,
                json_path,
                md_path,
                model_candidate,
                pyfunc_model_path,
                pyfunc_model_uri,
                bundle_path,
                bundle_evaluation_path,
                model_evaluation,
                thresholds_path,
                assessment_path,
                threshold_assessment,
                guidance_path,
                titration_guidance,
                plan_path,
                titration_plan,
                settings_handling_path,
                settings_special_handling,
            )
            log_metrics({
                'evidence_count': len(plan['evidence']),
                'recommended_command_count': len(plan['recommended_commands']),
                'hypothesis_count': len(plan['hypotheses']),
                'counter_causal_count': len(plan['counter_causal_findings']),
                'reasoning_correction_count': len(plan.get('reasoning_corrections', [])),
                'prioritized_follow_up_score': (
                    plan['prioritized_follow_up']['score'] if plan.get('prioritized_follow_up') else 0
                ),
                'readiness_score': evaluation['readiness_score'],
                'evidence_coverage_score': evaluation['evidence_coverage_score'],
                'retrieval_diversity_score': evaluation['retrieval_diversity_score'],
                'reasoning_correction_score': evaluation['reasoning_correction_score'],
                'model_schedule_coverage': (
                    model_evaluation['descriptive']['schedule_coverage_fraction']
                    if model_evaluation else 0
                ),
                'model_aggressive_basal_fraction': (
                    model_evaluation['safety']['aggressive_basal_fraction']
                    if model_evaluation else 0
                ),
                'promotion_validated': 1 if threshold_assessment and threshold_assessment['promotion_recommendation'] == 'validated' else 0,
                'guidance_reassessment_days': (
                    titration_guidance['reassessment_days'] if titration_guidance else 0
                ),
            })
            log_dict(plan, f'autoresearch/{json_path.name}')
            log_dict(trace_payload, f'genai/traces/{json_path.stem}_trace.json')
            log_dict(evaluation, f'genai/evals/{json_path.stem}_evaluation.json')
            if model_evaluation:
                log_dict(model_evaluation, f'models/evals/{json_path.stem}_bundle_evaluation.json')
            if threshold_assessment:
                log_dict(threshold_assessment, f'models/evals/{json_path.stem}_bundle_assessment.json')
            if titration_guidance:
                log_dict(titration_guidance, f'models/evals/{json_path.stem}_bundle_guidance.json')
            if titration_plan:
                log_dict(titration_plan, f'models/evals/{json_path.stem}_bundle_plan.json')
            if settings_special_handling:
                log_dict(settings_special_handling, f'models/evals/{json_path.stem}_bundle_settings_handling.json')
            log_artifact(json_path, artifact_path='autoresearch')
            log_artifact(md_path, artifact_path='autoresearch')
            if pyfunc_model_path:
                log_artifact(pyfunc_model_path.parent / f'{pyfunc_model_path.name}_candidate.json', artifact_path='models/pyfunc-support')
                log_artifact(pyfunc_model_path / 'MLmodel', artifact_path='models/pyfunc-local')
            if bundle_path:
                log_artifact(bundle_path, artifact_path='models/bundles')
            if bundle_evaluation_path:
                log_artifact(bundle_evaluation_path, artifact_path='models/evaluations')
            if thresholds_path:
                log_artifact(thresholds_path, artifact_path='models/thresholds')
            if assessment_path:
                log_artifact(assessment_path, artifact_path='models/assessments')
            if guidance_path:
                log_artifact(guidance_path, artifact_path='models/guidance')
            if plan_path:
                log_artifact(plan_path, artifact_path='models/plans')
            if settings_handling_path:
                log_artifact(settings_handling_path, artifact_path='models/settings-handling')
            if model_candidate:
                log_model_artifact(
                    model_candidate['candidate_name'],
                    model_candidate,
                    artifact_type='model-candidate',
                    artifact_path='models/candidates',
                    metadata={
                        'runner': 'autoresearch_agent',
                        'direction': direction,
                        'status': model_candidate['status'],
                        'registration_readiness': model_candidate['registration_readiness'],
                    },
                )
            span.set_inputs({'question': plan['question']})
            span.set_outputs({
                'json_path': str(json_path),
                'md_path': str(md_path),
                'readiness': evaluation['readiness'],
                'model_candidate_name': model_candidate['candidate_name'] if model_candidate else None,
                'pyfunc_model_uri': pyfunc_model_uri,
            })
            return {
                'plan': plan,
                'evaluation': evaluation,
                'model_candidate': model_candidate,
                'trace_payload': trace_payload,
                'pyfunc_model_path': pyfunc_model_path,
                'pyfunc_model_uri': pyfunc_model_uri,
                'bundle_path': bundle_path,
                'bundle_evaluation_path': bundle_evaluation_path,
                'model_evaluation': model_evaluation,
                'thresholds_path': thresholds_path,
                'assessment_path': assessment_path,
                'threshold_assessment': threshold_assessment,
                'guidance_path': guidance_path,
                'titration_guidance': titration_guidance,
                'plan_path': plan_path,
                'titration_plan': titration_plan,
                'settings_handling_path': settings_handling_path,
                'settings_special_handling': settings_special_handling,
                'json_path': json_path,
                'md_path': md_path,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--direction', choices=sorted(DIRECTIONS.keys()), required=True)
    parser.add_argument('--question', default=None, help='Optional custom research question')
    parser.add_argument('--output-dir', default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    result = run_direction(args.direction, question=args.question, output_dir=Path(args.output_dir))
    print(f"Saved JSON: {result['json_path']}")
    print(f"Saved memo: {result['md_path']}")


if __name__ == '__main__':
    main()
