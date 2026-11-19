"""Offline resolver: refusals fire at plan time, authored values continue, synthetic inputs only."""
import copy
import unittest
from unittest.mock import patch
import adapter as a
import runner
from test_run_configuration import config


class OfflineResolver(unittest.TestCase):
    def setUp(self):
        pin = patch.object(a, 'instrument', return_value={'sha256': 'd' * 64})
        pin.start()
        self.addCleanup(pin.stop)

    def to_completion(self, **prepare):
        value = copy.deepcopy(config())
        value['workSeconds'] = None
        value['tier'] = 'discovery'
        value['prepare'].update({'evaluator-catchup': 'fixed-target-v1', **prepare})
        return value

    def test_catchup_without_drain_window_fails_at_plan_time_before_any_actor(self):
        with patch.object(a, 'command', side_effect=AssertionError('actor started')):
            with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_TO_COMPLETION_PHASE_BUDGETS_REQUIRED'):
                runner.validate_config(self.to_completion())
            with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_TO_COMPLETION_PHASE_BUDGETS_REQUIRED'):
                runner.tier_plan(self.to_completion())

    def test_cleanup_600_is_accepted_and_explained_while_non_finite_is_refused(self):
        value = copy.deepcopy(config())
        value['cleanupSeconds'] = 600
        plan = runner.tier_plan(value)
        self.assertEqual(plan['effectiveLimits']['cleanupSeconds']['value'], 600)
        self.assertEqual(plan['effectiveLimits']['workSeconds']['value'], 720)
        self.assertEqual(plan['effectiveLimits']['drainSeconds']['origin'], 'run work deadline')
        for bad in (None, float('inf'), -1, 29, True):
            value['cleanupSeconds'] = bad
            with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_FINITE_LIMIT'):
                runner.validate_config(value)

    def test_compose_services_resolve_as_uncapped_and_say_so(self):
        plan = runner.tier_plan(copy.deepcopy(config()))
        self.assertNotIn('resources', plan['effective'])
        self.assertIn('uncapped', plan['resourceOrigin'])


if __name__ == '__main__':
    unittest.main()
