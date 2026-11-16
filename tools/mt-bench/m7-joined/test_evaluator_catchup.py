import copy
import unittest
from unittest import mock
import evaluator_catchup as c
import evaluator_progress as p
from test_evaluator_opportunities import BINDING
import test_evaluator_opportunities as fixtures
from test_evaluator_progress import A, B


class Catchup(unittest.TestCase):
    def setUp(self):
        self.boundary = fixtures.Opportunities().captures()[-1]
        self.boundary['rows'][0]['observed']['clock'] = '10'
        self.boundary['rows'][0]['completed']['clock'] = '10'
        self.now = 3_000_000_000

    def assess(self, snapshot):
        return c.assess(self.boundary, self.boundary, snapshot, [A, B], BINDING)

    def clock(self): return self.now
    def sleep(self, seconds): self.now += int(seconds * 1e9)

    def observe(self, snapshots, **kwargs):
        iterator = iter(snapshots)
        def fetch(timeout):
            self.assertGreater(timeout, 0)
            self.now += 100_000_000
            return next(iterator), {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
        return c.observe(self.boundary, [A, B], BINDING, fetch,
                         writer_stopped_ns=1_000_000_000, boundary_window={'startNs': 2_000_000_000, 'endNs': 2_100_000_000},
                         monotonic_ns=self.clock, sleep=self.sleep, **kwargs)

    def completed(self):
        value = copy.deepcopy(self.boundary)
        value['rows'][0]['observed']['clock'] = '12'
        value['rows'][0]['completed']['clock'] = '12'
        return value

    def test_intake_then_completion_of_same_frozen_target_without_output_change(self):
        value = self.assess(self.boundary)
        self.assertEqual(value['byTenant'][A]['awaitingObserved'], ['clock'])
        observed = self.completed(); observed['rows'][0]['completed']['clock'] = '10'
        self.assertEqual(self.assess(observed)['byTenant'][A]['awaitingCompleted'], ['clock'])
        result = self.observe([observed, self.completed()])
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['byTenant'][A]['targets'], {'clock': '12'})
        self.assertEqual(result['completionBounds'][A], {'lowerNs': 3_000_000_000, 'upperNs': 8_200_000_000})
        self.assertEqual(result['drainAfterWriterJoinMs'][A], {'lower': 2000.0, 'upper': 7200.0})
        self.assertEqual(result['byTenant'][A]['outputRevision'], self.boundary['rows'][0]['outputRevision'])

    def test_new_writer_or_metadata_never_moves_goalpost(self):
        for field in ('writerClock', 'metadata'):
            value = self.completed()
            if field == 'writerClock': value['rows'][0]['writerClock'] = '13'
            else: value['rows'][0]['observed']['settings'] = '2'
            result = self.observe([value])
            self.assertEqual(result['verdict'], 'FAIL')
            self.assertEqual(result['byTenant'][A]['status'], 'INPUT_CHANGED')
            self.assertEqual(result['byTenant'][A]['targets'], {'clock': '12'})

    def test_deadline_retains_pending_without_inventing_deadlock(self):
        result = self.observe([self.boundary] * 3, seconds=2, interval=1)
        self.assertEqual(result['verdict'], 'UNMEASURED')
        self.assertEqual(result['code'], 'M7_DRAIN_DEADLINE')
        self.assertEqual(len(result['captures']), 2)
        self.assertNotIn(A, result['completionBounds'])

    def test_restore_reset_coverage_and_binding_refuse_with_original_capture(self):
        cases = []
        for key, value in [('restoreGeneration', '1'), ('outputRevision', '1')]:
            item = self.completed(); item['rows'][0][key] = value; cases.append(item)
        item = self.completed(); item['rows'].pop(); cases.append(item)
        item = self.completed(); item['reader'] = {}; cases.append(item)
        for item in cases:
            result = self.observe([item])
            self.assertNotEqual(result['verdict'], 'PASS')
            self.assertEqual(result['captures'][0]['snapshot'], item)
            self.assertTrue(result['code'].startswith('M7_'))

    def test_query_budget_and_late_collection_cannot_earn_green(self):
        with mock.patch.dict(c.POLICY, maxQueries=0):
            result = self.observe([])
            self.assertEqual(result['code'], 'M7_DRAIN_QUERY_BOUND')
        def late(timeout):
            self.now += 2_000_000_000
            return self.completed(), {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
        result = c.observe(self.boundary, [A, B], BINDING, late, seconds=1, interval=1,
                           boundary_window={'startNs': 2_000_000_000, 'endNs': 2_100_000_000}, writer_stopped_ns=1_000_000_000,
                           monotonic_ns=self.clock, sleep=self.sleep)
        self.assertEqual(result['verdict'], 'UNMEASURED')
        self.assertEqual(result['code'], 'M7_DRAIN_DEADLINE')
        self.assertNotIn(A, result['completionBounds'])

    def test_boundary_cost_consumes_same_budget_and_reserve_precedes_fetch(self):
        cost = {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
        value = self.observe([self.completed()], initial_cost=cost)
        self.assertEqual(value['queries'], 2)
        self.assertEqual(value['responseBytes'], 256)
        self.assertEqual(value['rounds'], 2)
        with mock.patch.dict(c.POLICY, maxRounds=1):
            value = self.observe([], initial_cost=cost)
            self.assertEqual(value['rounds'], 1)
            self.assertEqual(value['captures'], [])
            self.assertEqual(value['code'], 'M7_DRAIN_QUERY_BOUND')
        self.now = 3_000_000_000
        with mock.patch.dict(c.POLICY, maxQueries=1):
            value = self.observe([], initial_cost=cost)
            self.assertEqual(value['queries'], 1)
            self.assertEqual(value['captures'], [])
            self.assertEqual(value['code'], 'M7_DRAIN_QUERY_BOUND')
        with mock.patch.dict(c.POLICY, maxBytes=128):
            value = self.observe([], initial_cost=cost)
            self.assertEqual(value['responseBytes'], 128)
            self.assertEqual(value['captures'], [])
            self.assertEqual(value['code'], 'M7_DRAIN_BYTE_BOUND')

    def test_changed_or_unknown_join_bracket_refuses(self):
        with self.assertRaisesRegex(p.Refused, 'WRITER_BOUNDARY'):
            c.observe(self.boundary, [A, B], BINDING, None,
                      boundary_window={'startNs': 0, 'endNs': 1}, writer_stopped_ns=2,
                      monotonic_ns=self.clock)

    def test_dropped_pending_and_moving_goalpost_controls_fail_then_restore(self):
        def criterion():
            self.assertEqual(self.assess(self.boundary)['byTenant'][A]['status'], 'PENDING')
        criterion()
        original = c.decode
        def drop_pending(*args):
            rows = copy.deepcopy(original(*args))
            rows[-1][A]['completed']['clock'] = rows[0][A]['writerClock']
            return rows
        with mock.patch.object(c, 'decode', side_effect=drop_pending):
            with self.assertRaises(AssertionError): criterion()
        criterion()
        changed = self.completed(); changed['rows'][0]['writerClock'] = '13'
        self.assertEqual(self.assess(changed)['verdict'], 'FAIL')


if __name__ == '__main__': unittest.main()
