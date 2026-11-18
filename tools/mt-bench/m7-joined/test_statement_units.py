import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import statement_units as su

OWNER = 'a' * 32
HOST = 'b' * 64
PAIR = {'core': 'c' * 40, 'deploy': 'd' * 40}
IMAGE = 'sha256:' + 'e' * 64
INCARNATION = '11111111-1111-4111-8111-111111111111'
ALLOCATION = {'version': 1, 'services': {'api': {'millicpus': 2000, 'memoryBytes': 2147483648}},
              'driver': {'millicpus': 4000, 'memoryBytes': 8589934592},
              'ceiling': {'millicpus': 20000, 'memoryBytes': 25769803776},
              'edge': {'workerProcesses': 1, 'workerConnections': 16384}}
CADENCE = {'offeredRps': 120.0, 'loadSeconds': 310, 'logicalPollingClients': 2000, 'probeEveryMs': 10000,
           'hotFactor': 1, 'accel': 1, 'socketsPerTenant': 2, 'idleSeconds': 30, 'warmupSeconds': 10}


def realtime(at, completed):
    return {'version': 1, 'owner': OWNER, 'hostIdentity': HOST, 'pair': PAIR, 'imageId': IMAGE, 'status': 'MEASURED',
            'services': {'realtime': {'status': 'MEASURED', 'processIncarnation': INCARNATION,
                                      'request': {'monotonicStartedAtNs': at, 'monotonicFinishedAtNs': at + 1000},
                                      'stats': {'version': 1, 'available': True, 'watchedCount': 10,
                                                'runtime': {'ticks': 1, 'refreshes': 1, 'detected': 1, 'detectFailures': 0},
                                                'detector': {'available': True, 'polls': 1, 'failures': 0},
                                                'delivery': {'received': completed, 'completed': completed, 'retries': 0, 'workQueries': 0,
                                                             'metadataUpdates': 0, 'metadataRows': 0, 'maxMetadataBatch': 1}}}}}


def timing(at):
    return {'clockDomain': 'collector-host-monotonic-v1',
            'reads': {'pg-role': {'status': 'PASS', 'monotonicStartedAtNs': at, 'monotonicFinishedAtNs': at + 10**8},
                      'pg-statements': {'status': 'PASS', 'monotonicStartedAtNs': at + 10**8, 'monotonicFinishedAtNs': at + 2 * 10**8}}}


def statement(role, calls, ms, qid):
    return '\t'.join([role, str(calls), str(ms), qid, '16384', 'SELECT 1'.encode().hex()])


class StatementUnits(unittest.TestCase):
    def point(self, root, *, allocation=ALLOCATION, cadence=CADENCE, evaluator_calls=6800, cycles=100):
        point = Path(root)
        load = point / 'load'
        load.mkdir(parents=True)
        (point / 'owner.json').write_text(json.dumps({'pair': PAIR, 'imageId': IMAGE, 'tenants': 1000, 'cadence': cadence,
                                                       'diagnosticResources': {'version': 1, 'profile': allocation}}))
        (load / 'before-pg-role.tsv').write_text('nsdemo_api\t1\t0.1\nnsdemo_evaluator\t1\t0.1\n')
        (load / 'before-pg-statements.tsv').write_text(statement('nsdemo_api', 1, 0.1, '1') + '\n' + statement('nsdemo_evaluator', 1, 0.1, '2') + '\n')
        roles = ['nsdemo_api\t2801\t900.1', 'nsdemo_evaluator\t%d\t900.1' % (evaluator_calls + 1), 'nsdemo_realtime\t2000\t200', 'postgres\t9\t9']
        (load / 'after-pg-role.tsv').write_text('\n'.join(roles) + '\n')
        rows = [statement('nsdemo_api', 2801, 900.1, '1'), statement('nsdemo_evaluator', evaluator_calls + 1, 900.1, '2'),
                statement('nsdemo_realtime', 2000, 200, '3'), statement('postgres', 9, 9, '4')]
        (load / 'after-pg-statements.tsv').write_text('\n'.join(rows) + '\n')
        (load / 'before-sql-snapshot-timing.json').write_text(json.dumps(timing(10**9)))
        (load / 'after-sql-snapshot-timing.json').write_text(json.dumps(timing(301 * 10**9)))
        (load / 'before-realtime-costs.json').write_text(json.dumps(realtime(10**9, 10)))
        (load / 'after-realtime-costs.json').write_text(json.dumps(realtime(301 * 10**9, 1010)))
        (load / 'evaluator-progress.json').write_text(json.dumps({'completedWorkDelta': cycles, 'completedTimeDelta': 0}))
        metrics = {'scenario_request_attempts': {'count': 100}}
        for shape in su.SHAPES:
            metrics['http_req_duration{shape:' + shape + '}'] = {'count': 100 // 7}
        (load / 'k6-summary.json').write_text(json.dumps({'metrics': metrics}))
        return point

    def test_units_and_ratios(self):
        with tempfile.TemporaryDirectory() as root:
            value = su.reduce(self.point(root))
        self.assertEqual(value['perUnit']['evaluator']['statementsPerUnit'], 68.0)
        self.assertEqual(value['perUnit']['api']['statementsPerUnit'], 28.0)
        self.assertEqual(value['perUnit']['realtime']['units'], 1000)
        self.assertEqual(value['perUnit']['realtime']['statementsPerUnit'], 2.0)
        self.assertNotIn('postgres', value['unattributedRoles'])
        self.assertEqual(value['sutTotals']['calls'], 2800 + 6800 + 2000)

    def test_timer_cycles_already_included_in_completed_work(self):
        # The native progress assemblers add acquisition and timer completions
        # into completedWorkDelta; completedTimeDelta is a subset, not extra work.
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            progress = point / 'load/evaluator-progress.json'
            progress.write_text(json.dumps({'completedWorkDelta': 100, 'completedTimeDelta': 5}))
            evaluator = su.reduce(point)['perUnit']['evaluator']
            self.assertEqual(evaluator['units'], 100)
            self.assertEqual(evaluator['statementsPerUnit'], 68.0)

    def test_corrupted_role_count_refuses_then_restores(self):
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            path = point / 'load/after-pg-role.tsv'
            original = path.read_text()
            self.assertEqual(su.reduce(point)['perUnit']['evaluator']['statements'], 6800)
            path.write_text(original.replace('nsdemo_evaluator\t6801', 'nsdemo_evaluator\t5801'))
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_ROLE_STATEMENT_MISMATCH'):
                su.reduce(point)
            path.write_text(original)
            self.assertEqual(su.reduce(point)['perUnit']['evaluator']['statements'], 6800)

    def test_corrupted_statement_count_refuses(self):
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            path = point / 'load/after-pg-statements.tsv'
            path.write_text(path.read_text().replace('nsdemo_api\t2801', 'nsdemo_api\t3801'))
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_ROLE_STATEMENT_MISMATCH'):
                su.reduce(point)

    def test_unit_count_changes_ratio(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(su.reduce(self.point(root, cycles=200))['perUnit']['evaluator']['statementsPerUnit'], 34.0)

    def test_busy_before_bookend_may_run_ahead(self):
        # Both bookends read roles first; a busy before-bookend lowers the delta.
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            path = point / 'load/before-pg-statements.tsv'
            path.write_text(path.read_text().replace('nsdemo_api\t1\t', 'nsdemo_api\t11\t'))
            self.assertEqual(su.reduce(point)['snapshotDrift']['byRole']['nsdemo_api']['calls'], -10)

    def test_reset_and_eviction_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            (point / 'load/before-pg-role.tsv').write_text('nsdemo_api\t99999\t0.1\nnsdemo_evaluator\t1\t0.1\n')
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_ROLE_RESET'):
                su.reduce(point)
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            path = point / 'load/after-pg-statements.tsv'
            path.write_text('\n'.join(l for l in path.read_text().splitlines() if not l.startswith('nsdemo_evaluator')) + '\n')
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_STATEMENT_EVICTED'):
                su.reduce(point)

    def test_comparison_refuses_cross_profile_and_workload(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = su.reduce(self.point(a))
            same = su.reduce(self.point(b))
            self.assertEqual(su.compare(first, same)['perUnit']['api']['statementsPerUnit'], {'before': 28.0, 'after': 28.0})
        other = copy.deepcopy(ALLOCATION)
        other['services']['api']['millicpus'] = 500
        with tempfile.TemporaryDirectory() as b:
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_PROFILE_MISMATCH'):
                su.compare(first, su.reduce(self.point(b, allocation=other)))
        with tempfile.TemporaryDirectory() as b:
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_PROFILE_NOT_EXPLICIT'):
                su.compare(first, su.reduce(self.point(b, allocation='local-qualification-external-pgstream-6cpu-10g-v1')))
        with tempfile.TemporaryDirectory() as b:
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_WORKLOAD_MISMATCH'):
                su.compare(first, su.reduce(self.point(b, cadence={**CADENCE, 'offeredRps': 180.0})))
        with tempfile.TemporaryDirectory() as b:
            with self.assertRaisesRegex(RuntimeError, 'M7_UNITS_WORKLOAD_MISMATCH'):
                su.compare(first, su.reduce(self.point(b, cadence={**CADENCE, 'probeEveryMs': 300000})))

    def test_clinical_floor_and_deadline_counts(self):
        def sample(upper, ready=True, frames=(100.0,)):
            return {'accepted': True, 'refused': False,
                    'durable': {'upperMs': upper, 'ready': True} if ready else None,
                    'clientFrames': [{'requestToFrameMs': f} for f in frames]}
        with tempfile.TemporaryDirectory() as root:
            point = self.point(root)
            path = point / 'load/probe.json'
            samples = [sample(1000.0 + i) for i in range(28)] + [sample(None, ready=False, frames=()), sample(130000.0, frames=(131000.0,))]
            strict = {'verdict': 'FAIL', 'witnesses': [{'ready': True}] * 27 + [{'ready': False, 'code': 'M7_COMPLETION_CLIENT'}] * 3}
            path.write_text(json.dumps({'durableOutputObservation': {'samples': samples}, 'completedOutput': strict, 'window': {'deliveredFrames': 29, 'expectedFrames': 60}}))
            c = su.reduce(point)['clinical']
            self.assertEqual(c['strictCompletion']['codes'], {'READY': 27, 'M7_COMPLETION_CLIENT': 3})
            self.assertEqual((c['accepted'], c['durableObserved'], c['deadlineMisses'], c['framesOver120s']), (30, 29, 2, 1))
            self.assertTrue(c['p95Qualified'])
            self.assertEqual(c['durableUpperMs']['max'], 130000.0)
            path.write_text(json.dumps({'durableOutputObservation': {'samples': samples[:29]}, 'window': {}}))
            self.assertFalse(su.reduce(point)['clinical']['p95Qualified'])
            path.unlink()
            self.assertEqual(su.reduce(point)['clinical']['status'], 'UNMEASURED')


if __name__ == '__main__':
    unittest.main()
