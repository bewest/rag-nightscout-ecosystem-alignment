import ast
import copy
from contextlib import contextmanager
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

import producer_startup as startup
import application_topology
import frozen


class Startup(unittest.TestCase):
    def test_role_diagnostic_keeps_only_the_source_contract(self):
        raw = b'Evaluator startup refused {"targetRole":"evaluator","checkPhase":"STREAM_STARTUP","causeCode":"UNCLASSIFIED"}'
        self.assertEqual(startup.role_diagnostics(raw), [
            {'targetRole': 'evaluator', 'checkPhase': 'STREAM_STARTUP', 'causeCode': 'UNCLASSIFIED'},
        ])
        extra = raw[:-1] + b',"message":"ignored"}'
        self.assertEqual(startup.role_diagnostics(extra), [])

    def test_cohort_window_selects_only_serving_cohort_and_keeps_ready_and_work_gates(self):
        source=Path(__file__).with_name('lifecycle.py')
        nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('ready','workload_ready','startup_window')]
        def attempt(window,work):
            clock=SimpleNamespace(now=0);clock.time=clock.monotonic=lambda:clock.now
            clock.sleep=lambda seconds:setattr(clock,'now',clock.now+seconds)
            pod={'metadata':{'labels':{'nightscout.org/run-id':'run'}},'status':{'conditions':[]}}
            observation={'uid':'pod','containers':[]};records={}
            def pods(_):
                if clock.now>=400:pod['status']['conditions']=[{'type':'Ready','status':'True'}]
                return [pod]
            scope={'time':clock,'work':work,'rid':'run','step':lambda *_:None,'owned':lambda:None,'pods':pods,
                   'application_topology':application_topology,'intent':{},'frozen':frozen,
                   'contextmanager':contextmanager,'phase_cutoff':None,
                   'summary':lambda _:observation,'producer_startup':startup,'put':lambda k,v:records.update({k:v})}
            exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),scope)
            return scope,records
        for window,work,pass_ in ((300,1000,False),(900,390,False),(900,1000,True)):
            scope,records=attempt(window,work)
            with scope['startup_window']('cohort',window):
                if pass_:
                    self.assertTrue(scope['ready']('cohort','cohort',window)['status']['conditions'])
                elif work>window:
                    # Window elapsed inside the work window: recorded signal, run continues.
                    self.assertIsNone(scope['ready']('cohort','cohort',window))
                    self.assertEqual(records['readiness-signal-cohort.json']['verdict'],'UNMEASURED')
                else:
                    # The run's own work deadline is still a hard stop.
                    with self.assertRaisesRegex(RuntimeError,'READY_DEADLINE_cohort'):
                        scope['ready']('cohort','cohort',window)
            self.assertEqual(records['startup-window-cohort.json']['effectiveWindowSeconds'],min(window,work))
        called=[]
        scope.update(ready=lambda *args:called.append(args), waits={'cohortReadySeconds':900,'workloadReadySeconds':600},producer_policy=None,
            objects=lambda stage:[{'kind':kind,'metadata':{'name':name},'spec':{'selector':{'matchLabels':{'role':name}}}}
                for kind,name in (('StatefulSet','cohort'),('Deployment','edge'),('Deployment','pgstream'))])
        scope['workload_ready']('serving')
        self.assertEqual([(r[1],r[2]) for r in called],[('cohort',900),('edge',600),('pgstream',600)])
        self.assertEqual(startup.cohort_ready_seconds({},7200),300)
        self.assertEqual(startup.cohort_ready_seconds({'cohortReadySeconds':900},7200),900)
        for value in (0,None,True,7201,1.5):
            with self.assertRaisesRegex(ValueError,'COHORT_READY_WINDOW'):
                startup.cohort_ready_seconds({'cohortReadySeconds':value},7200)

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
            'application_topology': application_topology, 'intent': {}, 'frozen': frozen,
            'time': clock, 'work': 30, 'phase_cutoff': None, 'rid': 'run', 'ns': 'synthetic',
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

    def test_native_webhook_codes_stay_line_scoped(self):
        self.assertEqual(startup.log_codes(b'webhook response status code: 503 Service Unavailable'),
                         ['OBSERVED_PRODUCER_RECEIVER_HTTP_503'])
        self.assertEqual(startup.log_codes(b'webhook did not respond\nstatus code: 503 unrelated'),
                         [])
        self.assertEqual(startup.log_codes(b'webhook request: dial tcp: connect: connection refused'),
                         ['OBSERVED_PRODUCER_RECEIVER_CONNECTION_REFUSED'])
        self.assertEqual(startup.log_codes(b'notifier is idle\nwebhook shutdown'), [])

    def test_actual_config_load_shape_maps_to_a_terminal_class(self):
        raw = b'Error: loading configuration: reading config file: open fixture.yaml: no such file'
        self.assertEqual(startup.log_codes(raw), ['OBSERVED_PRODUCER_CONFIG_LOAD_ERROR'])
        self.assertIn(startup.log_codes(raw)[0], startup.TERMINAL_CODES)
        self.assertEqual(startup.log_codes(b'webhook: context deadline exceeded'),
                         ['OBSERVED_PRODUCER_WEBHOOK_TIMEOUT'])
