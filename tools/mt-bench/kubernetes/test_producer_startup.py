import ast
import copy
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import producer_startup as startup
import scheduling
from primer_progress import ProgressWindow
import application_topology
import frozen


class Startup(unittest.TestCase):
    def test_scheduler_refusal_requires_the_observed_pod_identity(self):
        pod = {'metadata':{'name':'pgstream-pod'}, 'status':{'phase':'Pending', 'conditions':[
            {'type':'PodScheduled','status':'False','reason':'Unschedulable'}]}}
        self.assertEqual(scheduling.outcome(pod)['placement'], 'UNMEASURED')
        pod['metadata']['uid'] = 'observed-uid'
        self.assertEqual(scheduling.outcome(pod)['placement'], 'Unschedulable')
        pod['status']['conditions'] = []
        self.assertEqual(scheduling.outcome(pod)['placement'], 'Pending')
        pod['spec'] = {'nodeName':'worker'}
        self.assertEqual(scheduling.outcome(pod)['placement'], 'Scheduled')

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
            pod={'metadata':{'uid':'pod','name':'cohort-0','labels':{'nightscout.org/run-id':'run'}},
                 'spec':{'nodeName':'worker'}, 'status':{'conditions':[]}}
            observation={'uid':'pod','containers':[]};records={}
            def pods(_):
                if clock.now>=400:pod['status']['conditions']=[{'type':'Ready','status':'True'}]
                return [pod]
            scope={'ProgressWindow':ProgressWindow,'time':clock,'work':work,'rid':'run','step':lambda *_:None,'owned':lambda:None,'pods':pods,
                   'application_topology':application_topology,'intent':{},'frozen':frozen,
                   'contextmanager':contextmanager,'phase_cutoff':None,'scheduling':scheduling,'subprocess':subprocess,
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
            self.assertEqual(records['startup-window-cohort.json']['workUntilEpochSeconds'],min(window,work))
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

    def fixture(self, *, hard=False, changed_uid=False, output=b''):
        source = Path(__file__).with_name('lifecycle.py')
        nodes = [node for node in ast.parse(source.read_text()).body if isinstance(node, ast.FunctionDef)
                 and node.name in ('ready', 'failure_codes', 'require_pod_uid')]
        clock = SimpleNamespace(now=0)
        clock.time = clock.monotonic = lambda: clock.now
        clock.sleep = lambda seconds: setattr(clock, 'now', clock.now + seconds)
        acquired = []
        retained = {}
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous = {'reason': 'OOMKilled' if hard else 'Error', 'exitCode': 137 if hard else 1}
        container = {'name': 'pgstream', 'previousTermination': previous, 'restartCount': 1,
                     'state': {'waiting': {'reason': 'CrashLoopBackOff'}}}
        failed = {'uid': 'pod-id', 'name': 'pod', 'containers': [container]}
        ready = copy.deepcopy(failed)
        ready['containers'][0]['state'] = {'running': {}}
        pod = {'metadata': {'uid':'pod-id','name':'pod','labels': {'nightscout.org/run-id': 'run'}},
               'spec': {'nodeName':'worker'}, 'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        waiting = {**pod, 'status': {'conditions': []}}
        globals_ = {
            'ProgressWindow': ProgressWindow, 'application_topology': application_topology, 'intent': {}, 'frozen': frozen,
            'time': clock, 'work': 30, 'phase_cutoff': None, 'rid': 'run', 'ns': 'synthetic',
            'producer_startup': startup, 'rpc': ['kubectl'], 'subprocess': subprocess, 'scheduling': scheduling,
            'hashlib':hashlib,'os':os,'live':Path(directory.name),
            'owned': lambda: None, 'step': lambda _name: None,
            'pods': lambda _: [waiting] if clock.now < 2 else [pod],
            'summary': lambda value: failed if value is waiting else ready,
            'put': lambda name, value: retained.update({name: value}),
            'get': lambda *_args: {'metadata': {'uid': 'changed' if changed_uid else 'pod-id'}},
            'timestamp': lambda: clock.now,
        }

        def command(argv, **_kwargs):
            acquired.append(argv)
            return b'PGSTREAM_RETRY_SYNTHETIC' if '--previous' in argv else output

        globals_['command'] = command
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), globals_)
        return globals_['ready'], retained, acquired, pod

    def test_failed_container_keeps_bounded_private_log_without_publishing_its_bytes(self):
        output=b'x'*70000+b'\nprivate constructor detail\n'
        ready,records,calls,_=self.fixture(hard=True,output=output)
        with self.assertRaisesRegex(RuntimeError,'STARTUP_CONTAINER_FAILED_provision'):
            ready('provision','provision',20)
        attempt=records['failure-provision.json']['failed'][0]
        retained=attempt['currentLog']['privateLog']
        path=Path(retained['path'])
        self.assertEqual(path.read_bytes(),output[-65536:])
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertEqual(retained['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(retained['responseBytes'],len(output))
        self.assertTrue(retained['responseTruncated'])
        self.assertNotIn('private constructor detail',json.dumps(records))
        self.assertIn('--limit-bytes=65536',calls[0])
        previous=Path(attempt['previousLog']['privateLog']['path'])
        self.assertEqual(previous.read_bytes(),b'PGSTREAM_RETRY_SYNTHETIC')

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

