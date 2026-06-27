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

from .mlflow_utils import log_artifact, log_dict, log_metrics, start_run

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / 'externals' / 'experiments' / 'autoresearch'
RECENT_SWEEP = ROOT / 'externals' / 'experiments' / 'mlflow-initial-quick_results.json'

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
            'tools/cgmencode/run_validation_report.py',
        ),
        recommended_commands=(
            'python3 -m tools.cgmencode.run_research_reproduction correction-taxonomy',
            'python3 -m tools.cgmencode.run_research_reproduction settings-adequacy',
            'python3 -m tools.cgmencode.experiments_validated validate-hypo',
        ),
        hypotheses=(
            'Time-of-day basal decomposition is more actionable for settings changes than a global settings adequacy score.',
            'Correction taxonomy can distinguish where intervention quality is limited by slow correction, failed correction, or overcorrection risk.',
        ),
        success_criteria=(
            'Name the most actionable settings-focused next experiment or analysis.',
            'State which time scale is best for basal tuning versus correction assessment.',
            'Explain whether the next step is mainly tuning, triage, or safety-focused.',
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
        if spec.key == 'intervention-scoring':
            sweep = _load_recent_sweep_summary()
            if sweep:
                plan['recent_sweep'] = sweep
        if spec.key == 'proxy-scoping':
            plan['proxy_use_case_matrix'] = _build_proxy_use_case_matrix()
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
    lines.extend(['', '## Success Criteria', ''])
    lines.extend([f'- {item}' for item in plan['success_criteria']])
    lines.extend(['', '## Next Steps', ''])
    lines.extend([f'- {item}' for item in plan['next_steps']])
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return json_path, md_path


def run_direction(direction: str, question: str | None, output_dir: Path) -> dict[str, Any]:
    spec = DIRECTIONS[direction]
    with start_run(
        run_name=f'autoresearch-{direction}',
        tags={'runner': 'autoresearch_agent', 'surface': 'genai-pilot', 'direction': direction},
        params={'direction': direction, 'question': question or spec.default_question},
    ):
        with _span('autoresearch_request', span_type='AGENT', attributes={'direction': direction}) as span:
            plan = build_research_plan(direction, question=question)
            json_path, md_path = _write_outputs(plan, output_dir)
            log_metrics({
                'evidence_count': len(plan['evidence']),
                'recommended_command_count': len(plan['recommended_commands']),
                'hypothesis_count': len(plan['hypotheses']),
                'counter_causal_count': len(plan['counter_causal_findings']),
                'prioritized_follow_up_score': (
                    plan['prioritized_follow_up']['score'] if plan.get('prioritized_follow_up') else 0
                ),
            })
            log_dict(plan, f'autoresearch/{json_path.name}')
            log_artifact(json_path, artifact_path='autoresearch')
            log_artifact(md_path, artifact_path='autoresearch')
            span.set_inputs({'question': plan['question']})
            span.set_outputs({'json_path': str(json_path), 'md_path': str(md_path)})
            return {
                'plan': plan,
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
