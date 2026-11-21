"""Synthetic source replies through real strict reader/UID/caller paths; no cluster."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
import subprocess
import sys
from unittest.mock import Mock, patch

from test_adapter import fixture, iso, A, B
import kube_adapter as k
import execute
from workloads import profile

R = '33333333-3333-4333-8333-333333333333'
S = '44444444-4444-4444-8444-444444444444'


def page(ready=True, *, failed=(0, 0), runtime=R, acquisitions=1, generation=1):
    rows = []
    for tenant, count in zip((A, B), failed):
        rows.append({'tenant':tenant, 'admitted':True, 'ready':ready,
            'code':None if ready else 'EVALUATOR_CLINICAL_PROGRESS_STALLED', 'evaluation':{'alert':None},
            'cycles':acquisitions, 'progress':{'generation':generation, 'completedAcquisitions':acquisitions,
                'completedTimeCycles':0, 'failedCompletions':count, 'lastCompletedAgeMs':1 if acquisitions else None},
            'jobs':dict.fromkeys(k.evaluator_progress.JOB_FLAGS, False), 'dueAt':None, 'dueReason':None})
    return {'selected':[A, B], 'selfOrdinal':0, 'selfMode':'single', 'view':{'kind':'evaluator',
        'runtimeId':runtime, 'configured':{'ordinal':0, 'mode':'single'},
        'gate':{'eligible':True, 'reason':None}, 'tenants':rows}}


class Clock:
    def __init__(self): self.now = time.time()
    def time(self): return self.now
    def monotonic_ns(self): return int(self.now*1e9)
    def sleep(self, seconds): self.now += seconds


class ProgressCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name);self.out = self.d/'load';self.out.mkdir()
        self.c, self.inv, self.render, self.client = fixture()
        self.clock = Clock()
        self.c.update(tenants=2, tier='discovery')
        self.c['deadlines'] = {'workUntil':iso(self.clock.now+7200), 'cleanupUntil':iso(self.clock.now+7800)}
        self.objects = k.validate(self.c, self.inv, self.render)
        self.baseline = k.observe(self.c, self.objects, self.client)
        self.frames, self.calls, self.delay = [page(), page(), page()], 0, {}
        def call(*args, **kwargs):
            index = self.calls;self.calls += 1
            self.clock.now += self.delay.get(index, 0)
            value = self.frames[min(index, len(self.frames)-1)]
            if isinstance(value, BaseException): raise value
            return value if isinstance(value, bytes) else json.dumps(value).encode()+b'\n'
        self.client.call = Mock(side_effect=call)
        self.roster = [{'id':tenant, 'token':'synthetic', 'host':'synthetic.test'} for tenant in (A, B)]
        self.stack = __import__('contextlib').ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(k.time, 'time', self.clock.time))
        self.stack.enter_context(patch.object(k, 'active_baseline', return_value=self.baseline))
        self.load = self.stack.enter_context(patch.object(k, 'load', return_value=(self.d, self.c, self.objects)))
        self.stack.enter_context(patch.object(execute, 'roster', return_value=self.roster))

    def test_post_uid_check_runs_even_when_strict_decode_refuses(self):
        self.frames = [page(False)]
        def changed(*args, **kwargs):
            if self.client.call.called: raise k.Refused('K8S_POD_UID_CHANGED')
            return self.baseline
        with patch.object(k, 'observe', side_effect=changed):
            self.assertIsNone(execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, 'progress-before'))
        error = k.document(self.out/'progress-before-failure.json')
        self.assertEqual(error['code'], 'K8S_POD_UID_CHANGED')
        self.assertEqual(error['sourceRefusal']['diagnostic']['failedRow']['code'], 'EVALUATOR_CLINICAL_PROGRESS_STALLED')

    def initial_configuration(self):
        self.c.update(baseUrl='http://127.0.0.1:18080', tenantsFile='/synthetic/roster', settingsFingerprint='a'*64,
            workload={'loadSeconds':2, 'logicalPollingClients':0, 'probeEveryMs':3000, 'offeredRps':1},
            completion={'binding':{'kind':'evaluator-work-v2','pair':self.c['pins']['pair'],
                                  'imageId':self.c['pins']['appImageId'],'instrument':self.c['pins']['instrument']}})
        self.c['driver'].update(node='/synthetic/node', dependencies='/synthetic/deps', k6='/synthetic/k6', k6Sha256='b'*64)
        for name in ('probe.cjs', 'workload.js'): (self.d/name).write_text('synthetic')
        k.write(self.d/'packet.json', {'probe':{'kubernetesSha256':k.digest(self.d/'probe.cjs')},
                                      'workload':{'adaptedSha256':k.digest(self.d/'workload.js')}})

    def actual_client(self, *, delay=0, returncode=0, error=None, raw=None, stderr=b''):
        """Use Client.call unchanged; replace only its inert subprocess port."""
        tool = self.d/'kubectl';tool.write_text('inert; never executed\n')
        self.c.update(kubectl=str(tool), readonlyGuard='synthetic-readonly-guard')
        self.process_calls = []
        def run(argv, **kwargs):
            self.process_calls.append({'timeout':kwargs['timeout']})
            self.clock.now += delay
            if error: raise error
            frame = self.frames[min(self.calls, len(self.frames)-1)];self.calls += 1
            value = raw if raw is not None else json.dumps(frame).encode()+b'\n'
            return SimpleNamespace(returncode=returncode, stdout=value, stderr=stderr)
        self.client = k.Client(self.c, run=run)
        self.stack.enter_context(patch.object(k.shutil, 'which', return_value=str(tool)))
        self.observe = self.stack.enter_context(patch.object(k, 'observe', return_value=self.baseline))

    def test_actual_client_late_return_retains_bounded_response(self):
        self.actual_client(delay=20)
        execute.retained_progress(self.d, self.out, self.c, self.objects, self.client,
                                  'progress-before', until=self.clock.now+10)
        self.assertEqual(k.document(self.out/'progress-before-failure.json')['code'], 'K8S_OBSERVATION_DEADLINE')
        raw = self.out/'progress-before.private.jsonl'
        self.assertEqual(raw.read_bytes(), json.dumps(page()).encode()+b'\n')
        self.assertEqual(raw.stat().st_mode & 0o777, 0o600)
        response = k.document(self.out/'progress-before-response.json')
        self.assertEqual(response['captureBoundary'], 'client-response-sink')
        self.assertEqual(response['postObservation'], 'REFUSED')
        self.assertEqual(response['sourceDecode'], 'UNMEASURED')

    def test_actual_client_without_sink_preserves_default_deadline_order(self):
        self.actual_client(delay=2)
        with k.observation_deadline(self.clock.now+1):
            with self.assertRaisesRegex(k.Refused, 'K8S_OBSERVATION_DEADLINE'):
                self.client.call(['inert'], read=False, output_limit=1)

    def test_actual_client_nonzero_and_authorization_refusals_retain_returned_bytes(self):
        for name, stderr, code in [('exit', b'', 'K8S_OBSERVATION_LOST'),
                                   ('auth', b'EVALUATOR_SCOPE_UNSAFE', 'EVALUATOR_SCOPE_UNSAFE')]:
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0
                self.actual_client(returncode=1, stderr=stderr)
                self.assertIsNone(execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, 'progress'))
                self.assertEqual(k.document(self.out/'progress-failure.json')['code'], code)
                response = k.document(self.out/'progress-response.json')
                self.assertEqual(response['processReturnCode'], 1)
                self.assertFalse(response['transportSucceeded'])
                self.assertEqual(response['sourceDecode'], 'UNMEASURED')
                self.assertTrue((self.out/'progress.private.jsonl').is_file())

    def test_actual_client_oversized_or_partial_timeout_is_not_complete_capture(self):
        for name, kwargs, code in [('oversized', {'raw':b'x'*(k.evaluator_progress.POLICY['maxBytesPerPhase']//3+1)},
                                    'K8S_OBSERVATION_BOUND'),
                                   ('partial', {'error':subprocess.TimeoutExpired('inert', 1, output=b'partial')},
                                    'K8S_OBSERVATION_LOST')]:
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0;self.actual_client(**kwargs)
                self.assertIsNone(execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, 'progress'))
                self.assertEqual(k.document(self.out/'progress-failure.json')['code'], code)
                response = k.document(self.out/'progress-response.json')
                self.assertEqual(response['captureStatus'], 'UNAVAILABLE')
                self.assertFalse(response['responseRetained'])
                self.assertEqual(response['sourceDecode'], 'UNMEASURED')

    def test_initial_progress_refusal_is_recorded_and_the_stage_goes_on(self):
        # Progress is a figure (four-product-failures): a refused first capture never stops the stage.
        self.initial_configuration()
        self.frames = [page(False)]
        target = self.d/'load';target.rmdir()
        class Started(Exception):pass
        with patch.object(execute, 'actor', return_value={}), \
             patch.object(execute.subprocess, 'Popen', side_effect=Started):
            with self.assertRaises(Started):
                execute.execute(self.d, self.c, self.objects, self.client, load=True)
        failure = k.document(target/'progress-before-failure.json')
        self.assertEqual(failure['code'], 'M7_EVALUATOR_PROGRESS_ERROR')
        self.assertTrue(failure['responseRetained'])
        self.assertTrue((target/'runid').exists())

class Planning(unittest.TestCase):
    def test_legacy_preload_setting_neither_extends_work_window_nor_starts_an_observer(self):
        p = json.loads((Path(__file__).parent/'workloads/realistic-3000.json').read_text())
        p['phases']['preloadConvergence'] = {'contract':'strict-preload-convergence-v1',
                                             'seconds':18000, 'intervalSeconds':15}
        self.assertNotIn('preloadConvergence', profile.describe(p))

if __name__ == '__main__': unittest.main()
