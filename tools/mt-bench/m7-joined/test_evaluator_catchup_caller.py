"""Existing typed SQL reader and discovery tail, with SQL/RPC ports injected."""
import argparse
import contextlib
import discovery
import test_discovery
import evaluator_progress as progress
import copy
import json
import time
import unittest
from types import SimpleNamespace
from unittest import mock
import adapter as a
import evaluator_catchup as c
import evaluator_idle as idle
import test_evaluator_opportunity_caller as fixtures
from test_evaluator_progress import A, B


@unittest.skipUnless(fixtures.NODE.is_file(), 'qualified Node reader required')
class Caller(unittest.TestCase):
    def run_tail(self, *, writer_live=False, generation=False, deadline=True):
        owner = fixtures.Caller(); self.addCleanup(owner.doCleanups)
        directory, output, manifest, _, error, _, _ = owner.exercise()
        self.assertIsNone(error)
        manifest.update(evaluatorCatchup='fixed-target-v1')
        manifest['cadence']['restart'] = False
        original = a.document(output/'evaluator-progress.json')
        saved = (output/'evaluator-progress.json').read_bytes()
        rounds, _ = idle._decode(original, 2, ['evaluator'])
        frame = copy.deepcopy(rounds[-1])
        if generation: frame['owners'][A]['generation'] += 1
        a.write(output/'probe-accounting.json', {'admissionsClosed': True, 'byTenant': {A: {'pending': 0}}})
        stopped = time.monotonic_ns()
        record = SimpleNamespace(value={'processes': {k: {'returncode': 0, 'endMonoNs': stopped} for k in ('k6', 'probe')},
                                        'strictChecks': {'load': {'verdict': 'UNMEASURED', 'code': 'M7_OPPORTUNITY_NOT_OBSERVED'}}}, save=lambda: None)
        if writer_live: record.value['processes']['probe']['returncode'] = None
        _, _, _, row = owner.fixture()
        calls = []
        def sql(*args, **kwargs):
            calls.append(kwargs)
            values = [row(A, 2), row(B, 0)]
            if len(calls) == 1:
                values[0]['state']['observed']['clock'] = '10'; values[0]['state']['completed']['clock'] = '10'
                values[0]['typed']['observed'][0] = '10'; values[0]['typed']['completed'][0] = '10'
            return '\n'.join(json.dumps(r) for r in values)
        with mock.patch.object(a, 'progress_services', return_value=['evaluator']), mock.patch.object(a, 'psql', side_effect=sql), mock.patch.object(idle, 'round_view', return_value=frame):
            with a.command_deadline(time.time()+5 if deadline else None):
                value = c.run(a, directory, manifest, record)
        self.assertEqual((output/'evaluator-progress.json').read_bytes(), saved)
        self.assertEqual(record.value['strictChecks']['load']['verdict'], 'UNMEASURED')
        self.assertEqual(a.document(output/'evaluator-catchup.json'), value)
        return value, calls

    def test_real_typed_reader_tail_completes_frozen_target_and_preserves_load(self):
        value, calls = self.run_tail()
        self.assertEqual(value['verdict'], 'PASS')
        self.assertEqual(len(calls), 2)
        self.assertEqual(value['byTenant'][A]['targets'], {'clock': '12'})
        self.assertIn('NO-INSTRUMENT', value['authorityScope'])
        self.assertLessEqual(value['endNs']-value['startNs'], 5e9)
        self.assertTrue(all(row['timeout'] <= 5 for row in calls))

    def test_actual_generation_reset_refuses_and_retains_failed_boundary(self):
        value, calls = self.run_tail(generation=True)
        self.assertEqual(value['verdict'], 'FAIL')
        self.assertIn('RESET', value['code'])
        self.assertEqual(len(calls), 1)
        self.assertIn('snapshot', value['refusedCapture'])

    def test_no_tail_sql_until_writers_join_and_original_deadline_present(self):
        value, calls = self.run_tail(writer_live=True)
        self.assertEqual(value['code'], 'M7_DRAIN_WRITERS_NOT_JOINED'); self.assertEqual(calls, [])
        value, calls = self.run_tail(deadline=False)
        self.assertEqual(value['code'], 'M7_DRAIN_WORK_DEADLINE_REQUIRED'); self.assertEqual(calls, [])

    def test_optional_hook_runs_after_original_bookends_and_both_writer_joins(self):
        owner = test_discovery.Discovery(); self.addCleanup(owner.doCleanups)
        directory, manifest = owner.setup()
        manifest.update(evaluatorCatchup='fixed-target-v1', project='owned', port=1234, restartRoles=[],
                        settingsFingerprint={'sha256': 'a'*64}, generator={'tools': {'node': {'path': 'node'}}})
        record = discovery.Record(a, directory, manifest); events = []
        class Process:
            pid = 12345; returncode = 0
            def poll(self): return None
            def wait(self, timeout): events.append('probe-joined'); return 0
        def popen(*args, **kwargs):
            (directory/'load/.window').touch(); return Process()
        @contextlib.contextmanager
        def context(*args): yield
        def observed(*args):
            record.process('k6', lambda: events.append('k6-joined'))
            raise progress.Refused('M7_EVALUATOR_PROGRESS_NOT_OBSERVED')
        def tail(*args):
            self.assertIn('endMonoNs', record.value['processes']['k6'])
            self.assertIn('endMonoNs', record.value['processes']['probe'])
            events.append('tail')
        with contextlib.ExitStack() as stack:
            for name in ('psql', 'job_record', 'stop_job', 'quiet', 'assert_owned'):
                stack.enter_context(mock.patch.object(a, name))
            stack.enter_context(mock.patch.object(a, 'progress_services', return_value=['evaluator']))
            stack.enter_context(mock.patch.object(a, 'progress_attribution', return_value={}))
            stack.enter_context(mock.patch.object(a, 'sampling', context))
            stack.enter_context(mock.patch.object(a, 'loadgen_process', context))
            stack.enter_context(mock.patch.object(a, 'phase_snapshot', side_effect=lambda d, o, n: events.append(n)))
            stack.enter_context(mock.patch.object(a.subprocess, 'Popen', side_effect=popen))
            stack.enter_context(mock.patch.object(discovery, 'observed_load', side_effect=observed))
            stack.enter_context(mock.patch.object(c, 'run', side_effect=tail))
            discovery.discovery_load(a, directory, manifest, 'k6', record)
        self.assertEqual(events[-1], 'tail')
        self.assertLess(events.index('k6-joined'), events.index('after'))
        self.assertLess(events.index('after'), events.index('probe-joined'))
        self.assertLess(events.index('after-reconnect'), events.index('tail'))
        self.assertEqual(record.value['strictChecks']['load']['code'], 'M7_EVALUATOR_PROGRESS_NOT_OBSERVED')

    def test_explicit_discovery_without_restart_selection_only(self):
        m = {'profile': 'pgstream-sample', 'completionContract': 'evaluator-work-v2', 'runPurpose': 'discovery',
             'evaluatorOpportunities': 'received-input-v1', 'cadence': {'restart': False}}
        c.select(argparse.Namespace(), m); self.assertNotIn('evaluatorCatchup', m)
        c.select(argparse.Namespace(evaluator_catchup='fixed-target-v1'), m)
        for bad in [{**m, 'runPurpose': 'acceptance'}, {**m, 'cadence': {'restart': True}}]:
            with self.assertRaisesRegex(Exception, 'DRAIN_PROFILE'):
                c.select(argparse.Namespace(evaluator_catchup='fixed-target-v1'), bad)


if __name__ == '__main__': unittest.main()
