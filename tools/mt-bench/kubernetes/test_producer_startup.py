import ast
import copy
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

import producer_startup as startup


class Startup(unittest.TestCase):
    def fixture(self, *, hard=False, changed_uid=False):
        source = Path(__file__).with_name('lifecycle.py')
        nodes = [node for node in ast.parse(source.read_text()).body if isinstance(node, ast.FunctionDef)
                 and node.name in ('ready', 'failure_codes', 'require_pod_uid')]
        clock = SimpleNamespace(now=0)
        clock.time = clock.monotonic = lambda: clock.now
        clock.sleep = lambda seconds: setattr(clock, 'now', clock.now + seconds)
        acquired = []
        retained = {}
        previous = {'reason': 'OOMKilled' if hard else 'Error', 'exitCode': 137 if hard else 1}
        container = {'name': 'pgstream', 'previousTermination': previous, 'restartCount': 1,
                     'state': {'waiting': {'reason': 'CrashLoopBackOff'}}}
        failed = {'uid': 'pod-id', 'name': 'pod', 'containers': [container]}
        ready = copy.deepcopy(failed)
        ready['containers'][0]['state'] = {'running': {}}
        pod = {'metadata': {'labels': {'nightscout.org/run-id': 'run'}},
               'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        waiting = {**pod, 'status': {'conditions': []}}
        globals_ = {
            'time': clock, 'work': 30, 'rid': 'run', 'ns': 'synthetic',
            'producer_startup': startup, 'rpc': ['kubectl'], 'subprocess': subprocess,
            'owned': lambda: None, 'step': lambda _name: None,
            'pods': lambda _: [waiting] if clock.now < 2 else [pod],
            'summary': lambda value: failed if value is waiting else ready,
            'put': lambda name, value: retained.update({name: value}),
            'get': lambda *_args: {'metadata': {'uid': 'changed' if changed_uid else 'pod-id'}},
            'timestamp': lambda: clock.now,
        }

        def command(argv, **_kwargs):
            acquired.append(argv)
            return b'PGSTREAM_RETRY_SYNTHETIC' if '--previous' in argv else b''

        globals_['command'] = command
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), globals_)
        return globals_['ready'], retained, acquired, pod

    def test_bounded_retry_preserves_previous_log_and_waits_for_stability(self):
        ready, records, calls, expected = self.fixture()
        result = ready('only-producer', 'pgstream', 20, {'maxSeconds': 20, 'stableReadySeconds': 4})
        self.assertEqual(result, expected)
        self.assertEqual(records['failure-pgstream.json']['disposition'], 'RETRY')
        attempt = records['failure-pgstream.json']['failed'][0]
        self.assertEqual(attempt['previousLog']['codes'], ['PGSTREAM_RETRY_SYNTHETIC'])
        self.assertEqual(attempt['currentLog']['codes'], [])
        self.assertEqual(sum('--previous' in args for args in calls), 1)
        self.assertEqual(records['startup-convergence-pgstream.json']['observedStableSeconds'], 4)

    def test_hard_failure_legacy_failure_and_uid_change_refuse(self):
        ready, records, _calls, _ = self.fixture(hard=True)
        with self.assertRaisesRegex(RuntimeError, 'STARTUP_CONTAINER_FAILED_pgstream'):
            ready('only-producer', 'pgstream', 20, {'maxSeconds': 20, 'stableReadySeconds': 4})
        self.assertEqual(records['failure-pgstream.json']['disposition'], 'HARD')
        ready, _, _, _ = self.fixture()
        with self.assertRaisesRegex(RuntimeError, 'STARTUP_CONTAINER_FAILED_pgstream'):
            ready('only-producer', 'pgstream', 20)
        ready, _, calls, _ = self.fixture(changed_uid=True)
        with self.assertRaisesRegex(RuntimeError, 'POD_OWNERSHIP_CHANGED'):
            ready('only-producer', 'pgstream', 20, {'maxSeconds': 20, 'stableReadySeconds': 4})
        self.assertEqual(calls, [])

    def test_convergence_stays_within_the_authored_work_deadline(self):
        for options in ({'maxSeconds': 11, 'stableReadySeconds': 2},
                        {'maxSeconds': 10, 'stableReadySeconds': 10},
                        {'maxSeconds': 10, 'stableReadySeconds': True}):
            with self.assertRaisesRegex(ValueError, 'PRODUCER_STARTUP_WINDOW'):
                startup.policy(options, 10)
        ready, records, _, _ = self.fixture()
        with self.assertRaisesRegex(RuntimeError, 'READY_DEADLINE_pgstream'):
            ready('only-producer', 'pgstream', 5, {'maxSeconds': 5, 'stableReadySeconds': 4})
        self.assertNotIn('startup-convergence-pgstream.json', records)
