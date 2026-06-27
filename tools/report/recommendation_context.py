from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

ARTIFACT_FILENAMES = {
    'bundle_evaluation': 'effective-parameter-extractor_evaluation.json',
    'threshold_assessment': 'effective-parameter-extractor_assessment.json',
    'titration_guidance': 'effective-parameter-extractor_guidance.json',
    'titration_plan': 'effective-parameter-extractor_plan.json',
    'settings_special_handling': 'effective-parameter-extractor_settings_handling.json',
}


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def load_recommendation_context(
    report_dir: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    default_artifact_dir = root / 'externals' / 'experiments' / 'parameter-models'
    context: dict[str, Any] = {
        'pipeline': _load_json(report_dir / 'pipeline.json'),
        'facts': _load_json(report_dir / 'facts.json'),
        'artifacts': {},
        'artifact_paths': {},
    }

    for key, filename in ARTIFACT_FILENAMES.items():
        local_path = report_dir / filename
        default_path = default_artifact_dir / filename
        selected_path = local_path if local_path.exists() else default_path if default_path.exists() else None
        context['artifact_paths'][key] = str(selected_path) if selected_path else None
        context['artifacts'][key] = _load_json(selected_path)
    return context


def build_recommendation_status(
    patient_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    artifacts = context.get('artifacts', {})
    assessment = artifacts.get('threshold_assessment') or {}
    guidance = artifacts.get('titration_guidance') or {}
    plan = artifacts.get('titration_plan') or {}
    settings = artifacts.get('settings_special_handling') or {}
    evaluation = artifacts.get('bundle_evaluation') or {}

    patient_plan = (plan.get('per_patient') or {}).get(patient_id)
    promotion = assessment.get('promotion_recommendation') or guidance.get('promotion_recommendation')
    failed_gates = list(assessment.get('failed_gates', []))
    combined_cautions = list(settings.get('combined_cautions', []))
    carb_ratio_settings = (settings.get('settings') or {}).get('carb_ratio', {})

    return {
        'promotion_recommendation': promotion,
        'failed_gates': failed_gates,
        'max_basal_step_pct': guidance.get('max_basal_step_pct'),
        'reassessment_days': guidance.get('reassessment_days'),
        'concurrent_change_review_required': guidance.get('concurrent_change_review_required'),
        'review_required': bool(
            (patient_plan or {}).get('review_required')
            or promotion == 'needs-review'
        ),
        'patient_plan': patient_plan,
        'patient_action': (patient_plan or {}).get('staged_action'),
        'suggested_basal_step_pct': (patient_plan or {}).get('suggested_basal_step_pct'),
        'combined_cautions': combined_cautions,
        'carb_ratio_requires_meal_evidence': (
            ((carb_ratio_settings.get('evidence_loaded') or {}).get('depends_on_announced_meals'))
        ),
        'carb_ratio_promotion_ready_without_meals': carb_ratio_settings.get(
            'promotion_ready_without_meals'
        ),
        'median_tir': ((evaluation.get('safety') or {}).get('median_tir')),
        'artifact_paths': context.get('artifact_paths', {}),
    }


def build_policy_recommendation_item(status: dict[str, Any]) -> dict[str, Any] | None:
    promotion = status.get('promotion_recommendation')
    if not promotion:
        return None

    failed_gates = status.get('failed_gates', [])
    max_basal_step_pct = status.get('max_basal_step_pct')
    reassessment_days = status.get('reassessment_days')
    patient_action = status.get('patient_action') or 'review'
    review_required = status.get('review_required')

    if promotion == 'needs-review':
        priority = 'high'
        finding = 'Latest titration policy does not consider direct promotion safe without review.'
        recommendation = (
            f"Review first, then cap basal steps at {max_basal_step_pct}% and reassess after "
            f"{reassessment_days} days before broader changes."
            if max_basal_step_pct and reassessment_days
            else 'Review before applying broader basal or ISF changes.'
        )
    else:
        priority = 'info'
        finding = 'Latest titration policy supports a staged recommendation path.'
        recommendation = (
            f"Prefer the staged action `{patient_action}` and reassess after {reassessment_days} days."
            if reassessment_days
            else f"Prefer the staged action `{patient_action}`."
        )

    evidence_bits = []
    if failed_gates:
        evidence_bits.append('Failed gates: ' + ', '.join(failed_gates[:3]))
    if review_required and status.get('concurrent_change_review_required'):
        evidence_bits.append('Concurrent basal and ISF changes require explicit review.')
    if status.get('combined_cautions'):
        evidence_bits.append(status['combined_cautions'][0])

    return {
        'category': 'titration policy',
        'priority': priority,
        'finding': finding,
        'recommendation': recommendation,
        'evidence': ' '.join(evidence_bits) if evidence_bits else 'Derived from the latest parameter-model guidance artifacts.',
        'confirmable': 'Apply staged titration and review the next cycle before promotion.',
    }


def build_carb_ratio_caution_item(status: dict[str, Any]) -> dict[str, Any] | None:
    if not status.get('carb_ratio_requires_meal_evidence'):
        return None
    return {
        'category': 'carb ratio evidence',
        'priority': 'info',
        'finding': 'Current carb-ratio promotion still depends on announced meal evidence.',
        'recommendation': 'Do not promote carb-ratio changes from this report alone unless meal-conditioned evidence is available.',
        'evidence': 'Latest settings-handling artifacts mark carb-ratio evidence as announced-meal dependent.',
        'confirmable': 'Load meal-conditioned carb-ratio artifacts or review explicit meal examples before changing CR.',
    }


def build_recommendation_lists(
    *,
    pipeline_recs: list[dict[str, Any]],
    fallback_therapy_recs: list[dict[str, Any]],
    fallback_settings_recs: list[dict[str, Any]],
    status: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if pipeline_recs:
        priority_map = {1: 'high', 2: 'medium', 3: 'info'}
        therapy_recs_data = []
        recs_data = []
        for rec in pipeline_recs:
            priority = priority_map.get(rec.get('priority'), 'info')
            category = (rec.get('parameter') or rec.get('action_type') or 'recommendation').replace('_', ' ')
            finding = rec.get('description') or category.title()
            therapy_recs_data.append({
                'category': category,
                'priority': priority,
                'finding': finding,
                'recommendation': rec.get('rationale') or rec.get('description') or finding,
                'evidence': rec.get('evidence') or 'Canonical parquet-backed cgmencode recommendation.',
                'confirmable': 'Review against canonical report bundle.',
            })
            if rec.get('parameter'):
                recs_data.append({
                    'param': rec.get('parameter'),
                    'dir': rec.get('direction') or 'review',
                    'current': rec.get('current_value'),
                    'suggested': rec.get('suggested_value'),
                    'evidence': rec.get('evidence'),
                    'rationale': rec.get('rationale') or rec.get('description'),
                })
    else:
        therapy_recs_data = list(fallback_therapy_recs)
        recs_data = list(fallback_settings_recs)

    policy_rec = build_policy_recommendation_item(status)
    if policy_rec:
        therapy_recs_data.insert(0, policy_rec)
    carb_ratio_caution = build_carb_ratio_caution_item(status)
    if carb_ratio_caution:
        therapy_recs_data.append(carb_ratio_caution)
    return therapy_recs_data, recs_data


def apply_titration_policy_to_cards(
    decision_cards: list[dict[str, Any]],
    status: dict[str, Any],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    promotion = status.get('promotion_recommendation')
    max_basal_step_pct = status.get('max_basal_step_pct')
    reassessment_days = status.get('reassessment_days')
    review_required = status.get('review_required')
    concurrent_review = status.get('concurrent_change_review_required')
    patient_action = status.get('patient_action')

    if promotion:
        tone = 'danger' if promotion == 'needs-review' else 'warn'
        state = 'Unsafe without review' if promotion == 'needs-review' else 'Stage a smaller change first'
        expected_effect = (
            'Latest policy says the recommendation path is not promotion-ready yet.'
            if promotion == 'needs-review'
            else 'Latest policy supports a staged titration path instead of a direct full change.'
        )
        policy_card = {
            'title': 'Are these recommendations safe to apply directly?',
            'state': state,
            'tone': tone,
            'time_block': 'Titration policy',
            'confidence': {
                'total': 84 if promotion == 'needs-review' else 70,
                'label': 'High' if promotion == 'needs-review' else 'Moderate',
                'support': 80,
                'benefit_risk': 86 if promotion == 'needs-review' else 68,
                'agreement': 82 if promotion == 'needs-review' else 64,
            },
            'current': promotion.replace('-', ' ').title(),
            'suggested': (
                f"Use `{patient_action}` with <= {max_basal_step_pct}% basal steps"
                if patient_action and max_basal_step_pct
                else 'Review before applying broader setting changes'
            ),
            'expected_effect': expected_effect,
            'top_evidence': [
                'Latest parameter-model artifacts add promotion gates, titration guidance, and staged remediation plans.',
                'These outputs are more conservative than the older live report heuristics when safety gates fail.',
                'They are designed to turn large direct changes into staged, reviewable steps.',
            ],
            'risk': (
                'Applying the raw recommendation directly can outrun the latest safety policy.'
                if promotion == 'needs-review'
                else 'Even validated recommendations should still be staged and reassessed.'
            ),
            'automation_alt': (
                f"Reassess after {reassessment_days} days and prefer automation or narrower scope changes before all-day profile edits."
                if reassessment_days
                else 'Prefer narrower-scope automation changes before full-profile edits.'
            ),
        }
        cards.append(policy_card)

    for original in decision_cards:
        card = dict(original)
        title = str(card.get('title', '')).lower()
        if 'basal' in title and max_basal_step_pct:
            card['suggested'] = f"Review first, then <= {max_basal_step_pct}% basal step"
            if reassessment_days:
                card['risk'] = f"{card['risk']} Reassess after {reassessment_days} days before the next step."
            if review_required:
                card['state'] = 'Unsafe without review'
                card['tone'] = 'danger'
        elif ('isf' in title or 'correction' in title) and concurrent_review:
            card['risk'] = (
                f"{card['risk']} Concurrent basal and ISF pressure now requires explicit review "
                'before a broad profile change.'
            )
            if review_required:
                card['state'] = 'Needs more data before changing'
                card['tone'] = 'info'
        cards.append(card)
    return cards
