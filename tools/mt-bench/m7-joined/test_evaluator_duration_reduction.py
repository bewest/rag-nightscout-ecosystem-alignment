"""Pure retained-log controls; no runtime actor or performance claim."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import pool_diagnostics as p
import test_pool_diagnostics as fixtures


class EvaluatorDurations(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'retained-role.log'
        self.expected = {**copy.deepcopy(fixtures.EXPECTED), 'roles': ['evaluator']}

    def assess(self, rows, *, start=1000, end=3000):
        binding = fixtures.PoolDiagnostics.write(self, rows)
        binding['roles'] = ['evaluator']
        return p.assess(self.path, binding=binding, expected=self.expected, phase_start_ms=start, phase_end_ms=end)

    def rows(self, count=100):
        rows = [fixtures.source(1000), fixtures.source(3000, 4)]
        for index, row in enumerate(rows):
            row['roles'] = ['evaluator']
            for stage in p.EVALUATOR_STAGES:
                row['durations'][stage] = {'status': 'MEASURED' if index and count else 'UNMEASURED', 'count': count if index else 0,
                    'sumMs': 50 if index and count else 0, 'maxMs': 5 if index and count else 0, 'invalid': 0,
                    'buckets': [10, 40, 40, 9, 1, 0, 0, 0, 0, 0, 0, 0, 0] if index and count else [0] * len(p.BOUNDS)}
        return rows

    def test_three_optional_spans_preserve_attempt_scope_and_quantile_intervals(self):
        value = self.assess(self.rows())
        for stage in p.EVALUATOR_STAGES:
            duration = value['durations'][stage]
            self.assertEqual(duration['count'], 100)
            self.assertEqual(duration['countMeaning'], 'completed_call_attempts_including_rejections')
            self.assertEqual(duration['successfulWork']['status'], 'UNMEASURED')
            self.assertEqual(duration['quantileIntervalsMs']['p50']['lowerMs'], .1)
            self.assertEqual(duration['quantileIntervalsMs']['p50']['upperMs'], .5)
            self.assertEqual(duration['quantileIntervalsMs']['p95']['lowerMs'], 1)
            self.assertEqual(duration['quantileIntervalsMs']['p95']['upperMs'], 2)
            self.assertEqual(duration['quantileIntervalsMs']['p99']['upperMs'], 2)

    def test_old_baseline_absence_zero_attempts_and_unbounded_tail_remain_explicit(self):
        rows = self.rows()
        for row in rows:
            for stage in p.EVALUATOR_STAGES: row['durations'].pop(stage)
        result = self.assess(rows)
        self.assertTrue(all(result['durations'][stage]['status'] == 'NO-INSTRUMENT' for stage in p.EVALUATOR_STAGES))
        zero = self.assess(self.rows(0))
        self.assertTrue(all(zero['durations'][stage]['quantileIntervalsMs']['status'] == 'UNMEASURED' for stage in p.EVALUATOR_STAGES))
        quantile = p.quantile_intervals([0] * 12 + [1])['p95']
        self.assertEqual(quantile['lowerMs'], 5000); self.assertIsNone(quantile['upperMs']); self.assertTrue(quantile['upperUnbounded'])

    def test_reset_invalid_changed_presence_and_non_evaluator_roles_refuse(self):
        for mutate, expected in [
            (lambda r: r[1]['durations'][p.EVALUATOR_STAGES[0]].update(invalid=1), 'INVALID_HISTOGRAM'),
            (lambda r: r[0]['durations'].pop(p.EVALUATOR_STAGES[0]), 'CAPABILITY_CHANGED'),
            (lambda r: r[1]['durations'][p.EVALUATOR_STAGES[0]]['buckets'].__setitem__(0, 11), 'HISTOGRAM')]:
            rows = self.rows(); mutate(rows)
            with self.assertRaisesRegex(RuntimeError, expected): self.assess(rows)
        rows = self.rows(); rows.insert(1, copy.deepcopy(rows[1])); rows[1]['at'] = 2000
        rows[-1]['durations'][p.EVALUATOR_STAGES[0]] = copy.deepcopy(rows[0]['durations'][p.EVALUATOR_STAGES[0]])
        with self.assertRaisesRegex(RuntimeError, 'HISTOGRAM_RESET'): self.assess(rows)
        rows = self.rows(); rows[1]['roles'] = ['api']
        with self.assertRaisesRegex(RuntimeError, 'EVALUATOR_ROLE_REQUIRED'): self.assess(rows)

    def test_removing_three_actual_recognized_stages_is_red_not_silently_accepted(self):
        def criterion():
            result = self.assess(self.rows())
            self.assertTrue(all(result['durations'].get(stage, {}).get('count') == 100 for stage in p.EVALUATOR_STAGES))
        criterion()
        with mock.patch.object(p, 'STAGES', tuple(stage for stage in p.STAGES if stage not in p.EVALUATOR_STAGES)):
            with self.assertRaises(AssertionError): criterion()
        criterion()


if __name__ == '__main__': unittest.main()
