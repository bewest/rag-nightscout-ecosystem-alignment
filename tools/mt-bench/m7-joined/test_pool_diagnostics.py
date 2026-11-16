import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import pool_diagnostics as p


def source(at, count=1, *, held=True):
    histogram = {'status': 'MEASURED' if count else 'UNMEASURED', 'count': count, 'sumMs': count * 5, 'maxMs': 5 if count else 0, 'invalid': 0, 'buckets': [0, 0, 0, 0, count, 0, 0, 0, 0, 0, 0, 0, 0]}
    pools = {kind: {'status': 'MEASURED', 'tracked': 1, 'total': 1, 'idle': 1, 'checkedout': 0, 'waiting': 0, 'activeSQL': 0, 'sqlObservations': count, 'sqlStatus': 'MEASURED' if count else 'UNMEASURED', 'unsupportedQueryForms': 0} for kind in p.KINDS}
    coverage = {'pools': 'observed_pg_pools_only', 'directClients': 'UNMEASURED', 'sql': 'outstanding_client_query_calls'}
    if held:
        coverage['held'] = p.HELD_COVERAGE
        for row in pools.values():
            row.update(heldActive=0, heldObservations=count, heldStatus='MEASURED' if count else 'UNMEASURED', unsupportedHoldTracking=0)
    return {'version': 1, 'process': 123, 'coverage': coverage, 'roles': ['api'], 'rolesStatus': 'MEASURED', 'at': at,
            'pools': pools, 'poolOverflow': 0, 'unknownStages': 0, 'bucketsUpperMs': [0.1, 0.5, 1, 2, 5, 10, 20, 50, 100, 250, 1000, 5000, None],
            'durations': {stage: copy.deepcopy(histogram) for stage in p.STAGES if not stage.startswith('evaluator.') and (held or not stage.startswith('pool.held_'))}, 'gauges': {},
            'logging': {'status': 'MEASURED' if count else 'UNMEASURED', 'attempted': count + 1, 'written': count, 'dropped': 0, 'busy': 0, 'backpressure': 0, 'unavailable': 0, 'oversized': 0}}


EXPECTED = {'owner': 'a' * 32, 'hostIdentity': 'b' * 64, 'service': 'api-1', 'containerId': 'c' * 64,
            'startedAt': '2026-11-14T01:00:00.123456789Z', 'pair': {'core': 'd' * 40, 'deploy': 'e' * 40},
            'imageId': 'sha256:' + 'f' * 64, 'instrument': '1' * 64, 'roles': ['api']}


class PoolDiagnostics(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'retained-role.log'

    def write(self, rows, *, raw=None):
        if raw is None:
            raw = b'ordinary synthetic role output\n' + b''.join(p.PREFIX + json.dumps(row, separators=(',', ':')).encode() + b'\n' for row in rows)
        self.path.write_bytes(raw)
        return {**copy.deepcopy(EXPECTED), 'logSha256': hashlib.sha256(raw).hexdigest()}

    def assess(self, rows, *, start=1000, end=3000):
        binding = self.write(rows)
        return p.assess(self.path, binding=binding, expected=EXPECTED, phase_start_ms=start, phase_end_ms=end)

    def green(self):
        result = self.assess([source(1000), source(2000, 2), source(3000, 4)])
        self.assertEqual(result['status'], 'MEASURED')
        self.assertEqual(result['durations']['pool.held_storage']['count'], 3)
        self.assertEqual(result['durations']['pool.held_storage']['sumMs'], 15)
        self.assertEqual(result['durations']['pool.held_storage']['buckets'][4], 3)
        self.assertEqual(result['pools']['storage']['querySubmissions'], {'status': 'MEASURED', 'count': 3})
        return result

    def test_source_schema_observed_counter_histogram_deltas_and_raw_bytes_unchanged(self):
        result = self.green()
        self.assertEqual(result['observedMs'], {'first': 1000, 'last': 3000, 'elapsed': 2000, 'unobservedLeading': 0, 'unobservedTrailing': 0})
        self.assertEqual(result['durations']['api.authorize']['meanMs'], 5)
        self.assertEqual(result['durations']['pool.held_storage']['lifetimeMaxMs']['after'], 5)
        before = self.path.read_bytes()
        binding = {**copy.deepcopy(EXPECTED), 'logSha256': hashlib.sha256(before).hexdigest()}
        p.assess(self.path, binding=binding, expected=EXPECTED, phase_start_ms=1000, phase_end_ms=3000)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIn('not server executions or wire roundtrips', result['scope'])

    def test_subwindow_boundaries_are_explicit_and_outside_points_do_not_expand_phase(self):
        result = self.assess([source(900), source(1100, 2), source(2900, 4), source(3100, 5)])
        self.assertEqual(result['status'], 'OBSERVED_SUBWINDOW')
        self.assertEqual(result['samples'], 2)
        self.assertEqual(result['observedMs']['unobservedLeading'], 100)
        self.assertEqual(result['observedMs']['unobservedTrailing'], 100)
        self.assertEqual(result['durations']['pool.wait_storage']['count'], 2)
        binding = self.write([source(1000), source(3000, 4)])
        for first, last in ((True, 3000), (3000, 1000), (1000, 1000), (0, 3000)):
            with self.subTest(first=first, last=last), self.assertRaisesRegex(RuntimeError, 'PHASE_BOUNDARY'):
                p.assess(self.path, binding=binding, expected=EXPECTED, phase_start_ms=first, phase_end_ms=last)

    def test_missing_zero_or_single_samples_are_not_measured_cost(self):
        for rows in ([], [source(1000)], [source(900), source(3100, 4)]):
            with self.subTest(rows=len(rows)):
                value = self.assess(rows)
                self.assertEqual(value['status'], 'UNMEASURED')
                self.assertNotIn('durations', value)
        result = self.assess([source(1000, 0), source(3000, 0)])
        self.assertEqual(result['status'], 'UNMEASURED')
        self.assertEqual(result['durations']['pool.query_storage']['status'], 'UNMEASURED')
        self.assertIsNone(result['durations']['pool.query_storage']['meanMs'])
        self.assertEqual(result['pools']['storage']['querySubmissions']['status'], 'UNMEASURED')

    def test_old_source_held_absence_is_no_instrument_not_zero(self):
        result = self.assess([source(1000, held=False), source(3000, 4, held=False)])
        self.assertEqual(result['status'], 'MEASURED')
        for kind in p.KINDS:
            held = result['durations']['pool.held_' + kind]
            self.assertEqual(held['status'], 'NO-INSTRUMENT')
            self.assertNotIn('count', held)
            self.assertEqual(result['pools'][kind]['heldActive']['status'], 'NO-INSTRUMENT')

    def test_binding_and_raw_capture_mismatch_refuse_then_restore(self):
        self.green()
        binding = self.write([source(1000), source(3000, 4)])
        for key in p.IDENTITY:
            broken = copy.deepcopy(binding)
            broken[key] = ['realtime'] if key == 'roles' else {'core': '0' * 40, 'deploy': '0' * 40} if key == 'pair' else 'changed'
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'BINDING_MISMATCH'):
                p.assess(self.path, binding=broken, expected=EXPECTED, phase_start_ms=1000, phase_end_ms=3000)
        self.path.write_bytes(self.path.read_bytes() + b'changed capture\n')
        with self.assertRaisesRegex(RuntimeError, 'LOG_BINDING'):
            p.assess(self.path, binding=binding, expected=EXPECTED, phase_start_ms=1000, phase_end_ms=3000)
        self.green()

    def test_process_role_counter_reset_dropped_or_invalid_histogram_controls_restore(self):
        changes = [
            ('changed PID', lambda r: r.update(process=456), 'PROCESS_CHANGED'),
            ('wrong roles', lambda r: r.update(roles=['realtime']), 'ROLE_MISMATCH'),
            ('unknown roles', lambda r: r.update(rolesStatus='UNMEASURED'), 'ROLES_UNMEASURED'),
            ('version boolean', lambda r: r.update(version=True), 'VERSION'),
            ('log drop', lambda r: r['logging'].update(dropped=1), 'DROPPED'),
            ('log reset', lambda r: r['logging'].update(written=0, status='UNMEASURED'), 'LOGGING_RESET'),
            ('pool overflow', lambda r: r.update(poolOverflow=1), 'INCOMPLETE_COVERAGE'),
            ('unknown stage', lambda r: r.update(unknownStages=1), 'INCOMPLETE_COVERAGE'),
            ('pool reset', lambda r: r['pools']['storage'].update(sqlObservations=0, sqlStatus='UNMEASURED'), 'COUNTER_RESET'),
            ('pool roster', lambda r: r['pools']['storage'].update(tracked=2), 'POOL_ROSTER_CHANGED'),
            ('bad histogram buckets', lambda r: r['durations']['pool.wait_storage']['buckets'].__setitem__(0, 1), 'HISTOGRAM'),
            ('invalid timer', lambda r: r['durations']['pool.wait_storage'].update(invalid=1), 'INVALID_HISTOGRAM'),
            ('negative histogram', lambda r: r['durations']['pool.wait_storage'].update(sumMs=-1), 'HISTOGRAM'),
            ('capability changed', lambda r: r['durations'].pop('pool.held_storage'), 'HELD_CAPABILITY'),
            ('source bucket boundaries', lambda r: r['bucketsUpperMs'].__setitem__(0, 0.2), 'BUCKET_BOUNDARIES')]
        for name, mutate, code in changes:
            self.green()
            rows = [source(1000), source(2000, 2), source(3000, 4)]
            mutate(rows[1])
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, code):
                self.assess(rows)
            self.green()
        # Reset and recover before the last bookend is still refused.
        rows = [source(1000), source(2000, 2), source(3000, 4)]
        rows[1]['durations']['api.authorize'] = source(2000, 0)['durations']['api.authorize']
        with self.assertRaisesRegex(RuntimeError, 'HISTOGRAM_RESET'):
            self.assess(rows)
        self.green()
        with self.assertRaisesRegex(RuntimeError, 'SAMPLE_ORDER'):
            self.assess([source(1000), source(1000, 2), source(3000, 4)])
        self.green()

    def test_missing_coverage_is_not_zero_and_unsupported_queries_not_green(self):
        rows = [source(1000), source(3000, 4)]
        for row in rows:
            row['pools']['storage'].update(unsupportedQueryForms=1, sqlStatus='UNMEASURED', unsupportedHoldTracking=1, heldStatus='UNMEASURED')
        result = self.assess(rows)
        self.assertEqual(result['durations']['pool.query_storage']['status'], 'UNMEASURED')
        self.assertEqual(result['durations']['pool.held_storage']['status'], 'UNMEASURED')
        self.assertEqual(result['pools']['storage']['querySubmissions']['status'], 'UNMEASURED')
        rows[0]['pools']['operation'].update(status='UNMEASURED', sqlStatus='UNMEASURED', heldStatus='UNMEASURED')
        self.assertEqual(self.assess(rows)['durations']['pool.wait_operation']['status'], 'UNMEASURED')

    def test_malformed_duplicate_oversize_lines_fail_without_echoing_private_content(self):
        for raw, code in ((p.PREFIX + b'{"private":"do not echo"}\n', 'PROCESS_TIME'),
                          (p.PREFIX + b'{bad private detail}\n', 'JSON'),
                          (p.PREFIX + b'{"at":1000,"at":2000}\n', 'DUPLICATE_FIELD'),
                          (p.PREFIX + b' ' * p.MAX_LINE_BYTES, 'LOG_BOUND')):
            binding = self.write([], raw=raw)
            with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, code) as found:
                p.assess(self.path, binding=binding, expected=EXPECTED, phase_start_ms=1000, phase_end_ms=3000)
            self.assertNotIn('private', str(found.exception))
        self.green()


if __name__ == '__main__':
    unittest.main()
