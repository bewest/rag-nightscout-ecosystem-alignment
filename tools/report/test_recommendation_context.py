import json
import tempfile
import unittest
from pathlib import Path

from tools.report.recommendation_context import (
    apply_titration_policy_to_cards,
    build_policy_recommendation_item,
    build_recommendation_lists,
    build_recommendation_status,
    load_recommendation_context,
)


class TestRecommendationContext(unittest.TestCase):
    def test_load_recommendation_context_prefers_local_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            report_dir = Path(d)
            (report_dir / 'pipeline.json').write_text(json.dumps({'patient_id': 'a'}), encoding='utf-8')
            (report_dir / 'facts.json').write_text(json.dumps({'days_of_data': 14}), encoding='utf-8')
            (report_dir / 'effective-parameter-extractor_assessment.json').write_text(
                json.dumps({'promotion_recommendation': 'needs-review', 'failed_gates': ['safety.concurrent_change_fraction']}),
                encoding='utf-8',
            )
            context = load_recommendation_context(report_dir, root=report_dir)
            self.assertEqual(context['pipeline']['patient_id'], 'a')
            self.assertEqual(context['facts']['days_of_data'], 14)
            self.assertEqual(
                context['artifacts']['threshold_assessment']['promotion_recommendation'],
                'needs-review',
            )

    def test_build_recommendation_status_extracts_patient_plan(self):
        context = {
            'artifact_paths': {},
            'artifacts': {
                'threshold_assessment': {
                    'promotion_recommendation': 'needs-review',
                    'failed_gates': ['safety.basal_over_ten_pct_fraction'],
                },
                'titration_guidance': {
                    'max_basal_step_pct': 10,
                    'reassessment_days': 3,
                    'concurrent_change_review_required': True,
                },
                'titration_plan': {
                    'per_patient': {
                        'a': {
                            'staged_action': 'review-basal-first',
                            'review_required': True,
                            'suggested_basal_step_pct': 10,
                        }
                    }
                },
                'settings_special_handling': {
                    'combined_cautions': ['Carb-ratio handling still depends on announced meals.'],
                    'settings': {
                        'carb_ratio': {
                            'evidence_loaded': {'depends_on_announced_meals': True},
                            'promotion_ready_without_meals': False,
                        }
                    },
                },
                'bundle_evaluation': {'safety': {'median_tir': 0.66}},
            },
        }
        status = build_recommendation_status('a', context)
        self.assertEqual(status['promotion_recommendation'], 'needs-review')
        self.assertEqual(status['patient_action'], 'review-basal-first')
        self.assertTrue(status['review_required'])
        self.assertTrue(status['carb_ratio_requires_meal_evidence'])

    def test_apply_titration_policy_to_cards_adds_policy_card_and_rewrites_basal(self):
        cards = [{
            'title': 'Should overnight basal change?',
            'state': 'Stage a smaller change first',
            'tone': 'warn',
            'time_block': 'Overnight',
            'confidence': {'total': 60, 'label': 'Moderate', 'support': 60, 'benefit_risk': 60, 'agreement': 60},
            'current': '0.80 U/hr',
            'suggested': '0.88 U/hr',
            'expected_effect': '+2.0 pp TIR',
            'top_evidence': ['e1'],
            'risk': 'Original risk.',
            'automation_alt': 'Original automation option.',
        }]
        status = {
            'promotion_recommendation': 'needs-review',
            'max_basal_step_pct': 10,
            'reassessment_days': 3,
            'review_required': True,
            'concurrent_change_review_required': True,
            'patient_action': 'review-basal-first',
            'failed_gates': ['safety.concurrent_change_fraction'],
            'combined_cautions': ['Caution.'],
        }
        updated = apply_titration_policy_to_cards(cards, status)
        self.assertEqual(updated[0]['title'], 'Are these recommendations safe to apply directly?')
        self.assertEqual(updated[1]['state'], 'Unsafe without review')
        self.assertIn('<= 10% basal step', updated[1]['suggested'])
        self.assertIn('Reassess after 3 days', updated[1]['risk'])

    def test_build_policy_recommendation_item_reflects_review_state(self):
        item = build_policy_recommendation_item({
            'promotion_recommendation': 'needs-review',
            'failed_gates': ['safety.concurrent_change_fraction'],
            'max_basal_step_pct': 10,
            'reassessment_days': 3,
            'patient_action': 'review-basal-first',
            'review_required': True,
            'concurrent_change_review_required': True,
            'combined_cautions': ['Caution.'],
        })
        self.assertIsNotNone(item)
        self.assertEqual(item['category'], 'titration policy')
        self.assertIn('10%', item['recommendation'])

    def test_build_recommendation_lists_uses_pipeline_when_present(self):
        therapy_recs, settings_recs = build_recommendation_lists(
            pipeline_recs=[{
                'priority': 1,
                'parameter': 'isf',
                'action_type': 'adjust_isf',
                'description': 'Pipeline says correction behavior should change.',
                'rationale': 'Use a staged ISF update.',
                'evidence': 'Pipeline evidence.',
                'direction': 'increase',
                'current_value': 40.0,
                'suggested_value': 44.0,
            }],
            fallback_therapy_recs=[{'category': 'basal', 'finding': 'fallback'}],
            fallback_settings_recs=[{'param': 'basal'}],
            status={},
        )
        self.assertEqual(therapy_recs[0]['category'], 'isf')
        self.assertEqual(settings_recs[0]['param'], 'isf')

    def test_build_recommendation_lists_adds_policy_overlay_to_fallback(self):
        therapy_recs, settings_recs = build_recommendation_lists(
            pipeline_recs=[],
            fallback_therapy_recs=[{'category': 'basal', 'finding': 'fallback'}],
            fallback_settings_recs=[{'param': 'basal'}],
            status={
                'promotion_recommendation': 'needs-review',
                'failed_gates': ['safety.concurrent_change_fraction'],
                'max_basal_step_pct': 10,
                'reassessment_days': 3,
                'review_required': True,
                'concurrent_change_review_required': True,
                'combined_cautions': ['Caution.'],
            },
        )
        self.assertEqual(therapy_recs[0]['category'], 'titration policy')
        self.assertEqual(settings_recs[0]['param'], 'basal')


if __name__ == '__main__':
    unittest.main()
