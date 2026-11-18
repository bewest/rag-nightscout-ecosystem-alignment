"""Synthetic source replies through real strict reader/UID/caller paths; no cluster."""
import copy
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
import preload
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


class Preload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name);self.out = self.d/'load';self.out.mkdir()
        self.c, self.inv, self.render, self.client = fixture()
        self.clock = Clock()
        self.c.update(tenants=2, tier='discovery', preloadConvergence={'contract':preload.shared.CONTRACT,
            'seconds':10, 'intervalSeconds':1})
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

    def run_phase(self):
        return preload.run(self.d, self.out, self.c, self.objects, self.client,
                           ids=[row['id'] for row in self.roster], collect=execute.retained_progress, clock=self.clock)

    def result(self): return k.document(self.out/'preload-convergence/result.json')

    def fresh(self, state):
        value = execute.retained_progress(self.d, self.out, self.c, self.objects, self.client,
                                          'progress-before', until=state['until'])
        preload.fresh(self.out, self.c, value, state)

    def test_transient_strict_failure_two_passes_and_fresh_third(self):
        self.frames = [page(False), page(), page(), page()]
        state = self.run_phase();self.fresh(state)
        self.assertEqual(self.result()['strictStartupVerdicts'], {'PASS':2, 'FAIL':1, 'UNMEASURED':0})
        sample = self.out/'preload-convergence/sample-0000'
        refusal = k.document(sample/'progress-failure.json')
        self.assertEqual(refusal['diagnostic']['failedRow']['code'], 'EVALUATOR_CLINICAL_PROGRESS_STALLED')
        self.assertEqual((sample/'progress.private.jsonl').stat().st_mode & 0o777, 0o600)
        self.assertEqual(k.document(self.out/'preload-convergence/fresh-readiness.json')['verdict'], 'PASS')
        self.assertEqual(self.calls, 4)

    def test_persistent_unready_expires_and_original_work_clips_large_selection(self):
        self.frames = [page(False)]
        self.c['preloadConvergence']['seconds'] = 3600
        self.c['deadlines']['workUntil'] = iso(self.clock.now+3)
        with self.assertRaisesRegex(k.Refused, 'CONVERGENCE_EXPIRED'):
            self.run_phase()
        self.assertEqual(self.result()['status'], 'REFUSED')
        self.assertEqual(self.result()['window']['clippedBy'], ['original-work'])
        self.assertTrue(all(v['verdict'] == 'FAIL' for v in self.result()['samples']))

    def test_no_fixed_eighty_sample_ceiling(self):
        self.c['preloadConvergence'].update(seconds=3600, intervalSeconds=15)
        self.frames = [page(False)]*90+[page(), page()]
        self.run_phase()
        self.assertEqual(len(self.result()['samples']), 92)
        self.assertGreater(self.result()['maxScheduledSamples'], 80)

    def test_selected_phase_reaches_warmup_after_legacy_load_cap(self):
        self.c['preloadConvergence'].update(seconds=10000, intervalSeconds=30)
        self.c['deadlines'] = {'workUntil':iso(self.clock.now+12000), 'cleanupUntil':iso(self.clock.now+12600)}
        started = self.clock.now
        self.frames = [page(False)]*241+[page(), page()]
        self.run_phase()
        self.assertGreater(self.clock.now-started, 7200)
        self.assertEqual(self.result()['stopReason'], 'stable-strict-bracket')

    def test_selected_capture_policy_is_used_in_strict_bracket_and_fresh_read(self):
        selected = {'maxQueriesPerPhase':1200, 'maxBytesPerPhase':80000000}
        self.c['workload'] = {'evaluatorProgressBudget':selected}
        original = k.evaluator_progress.assess
        with patch.object(k.evaluator_progress, 'assess', wraps=original) as assess:
            state = self.run_phase();self.fresh(state)
        self.assertEqual(assess.call_args.kwargs['policy'], k.evaluator_progress.capture_policy(selected))
        self.assertEqual(self.result()['capturePolicy']['maxQueriesPerPhase'], 1200)

    def test_historical_counter_is_retained_without_qualification_pass(self):
        self.frames = [page(failed=(3, 0))]*3
        state = self.run_phase();self.fresh(state)
        self.assertEqual(self.result()['historicalFailedTotal'], 3)
        self.assertEqual(self.result()['evaluationProgressQualification']['verdict'], 'FAIL')
        self.assertEqual(self.result()['status'], 'EXECUTION_READY')

    def test_typed_transient_increase_is_counted_and_untyped_increase_refused(self):
        import outcome_gate
        typed = page(failed=(1, 0))
        typed['view']['failureReasonContract'] = outcome_gate.TYPED_CONTRACT
        typed['view']['tenants'][0]['progress'].update(failureReasons={'startup-warming':1},
                                                       unresolvedFailure=None, maxFailureResolutionMs=900)
        for row in typed['view']['tenants'][1:]:
            row['progress'].update(failureReasons={}, unresolvedFailure=None, maxFailureResolutionMs=None)
        preload.compare_failed({A:0, B:0}, {A:1, B:0}, (json.dumps(typed)+'\n').encode())
        with self.assertRaisesRegex(k.Refused, 'FAILED_COUNTER_INCREASED'):
            preload.compare_failed({A:0, B:0}, {A:1, B:0}, (json.dumps(page(failed=(1, 0)))+'\n').encode())
        hard = copy.deepcopy(typed)
        hard['view']['tenants'][0]['progress']['failureReasons'] = {'worker-unavailable':1}
        with self.assertRaisesRegex(k.Refused, 'FAILED_COUNTER_INCREASED'):
            preload.compare_failed({A:0, B:0}, {A:1, B:0}, (json.dumps(hard)+'\n').encode())

    def test_per_tenant_increase_decrease_and_offset_cannot_hide(self):
        for second, code in (((4, 1), 'INCREASED'), ((2, 0), 'DECREASED'), ((2, 2), 'DECREASED')):
            with self.subTest(second=second):
                self.out = self.d/('counts-'+str(second));self.out.mkdir()
                self.calls = 0;self.frames = [page(failed=(3, 1)), page(failed=second)]
                with self.assertRaisesRegex(k.Refused, 'FAILED_COUNTER_'+code): self.run_phase()
                self.assertEqual(len(self.result()['samples']), 2)

    def test_third_round_counter_drift_and_reset_refuse_before_driver(self):
        state = self.run_phase()
        self.frames = [page(failed=(1, 0))];self.calls = 0
        with self.assertRaisesRegex(k.Refused, 'FAILED_COUNTER_INCREASED'): self.fresh(state)
        self.assertEqual(k.document(self.out/'preload-convergence/fresh-readiness.json')['verdict'], 'FAIL')
        self.assertTrue((self.out/'progress-before.private.jsonl').is_file())

    def test_runtime_reset_and_generation_rewind_refuse(self):
        for name, second in [('runtime', page(runtime=S)), ('generation', page(generation=0))]:
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0;self.frames = [page(), second]
                with self.assertRaisesRegex(RuntimeError, 'RUNTIME_CHANGED' if name=='runtime' else 'COUNTER_REWOUND'):
                    self.run_phase()

    def test_forward_generation_and_successful_counters_are_permitted(self):
        self.frames = [page(), page(generation=2, acquisitions=2), page(generation=3, acquisitions=3)]
        state = self.run_phase();self.fresh(state)
        self.assertEqual(self.result()['status'], 'EXECUTION_READY')

    def test_hidden_poison_after_transient_is_not_observed_as_warmup(self):
        for name, key, value in [('unknown-code', 'code', 'EVALUATOR_CONFIG_REFUSED'),
                                 ('alert', 'evaluation', {'alert':'poison'}),
                                 ('invalid-counter', 'progress', {'failedCompletions':-1})]:
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0
                frame = page(False);row = frame['view']['tenants'][1]
                row[key] = {**row[key], **value} if key == 'progress' else value
                self.frames = [frame]
                with self.assertRaises((RuntimeError, k.Refused)): self.run_phase()
                self.assertEqual(len(self.result()['samples']), 1)

    def test_hidden_missing_or_foreign_tenant_after_transient_refuses_first_sample(self):
        for name in ('missing', 'foreign'):
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0
                frame = page(False)
                if name == 'missing':
                    frame['selected'].pop();frame['view']['tenants'].pop()
                else:
                    frame['selected'][1] = R;frame['view']['tenants'][1]['tenant'] = R
                self.frames = [frame]
                started = self.clock.now
                with self.assertRaisesRegex(k.Refused, 'PRELOAD_ROSTER_CHANGED'): self.run_phase()
                self.assertEqual(self.calls, 1)
                self.assertEqual(self.clock.now, started)

    def test_transport_and_malformed_capture_are_separate_from_convergence(self):
        for name, value, code in [('transport', k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED'), 'SOURCE_UNMEASURED'),
                                   ('malformed', b'{not json}\n', 'SOURCE_CONTRACT')]:
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0;self.frames = [value]
                with self.assertRaisesRegex((k.Refused, RuntimeError), code): self.run_phase()
                self.assertEqual(len(self.result()['samples']), 1)

    def test_late_second_success_is_retained_but_never_admitted(self):
        self.delay[1] = 20
        with self.assertRaisesRegex(k.Refused, 'OBSERVATION_DEADLINE'): self.run_phase()
        self.assertEqual(self.result()['status'], 'REFUSED')
        late = self.out/'preload-convergence/sample-0001'
        self.assertTrue((late/'progress.private.jsonl').is_file())
        self.assertEqual(k.document(late/'progress-response.json')['postObservation'], 'REFUSED')

    def test_post_uid_check_runs_even_when_strict_decode_refuses(self):
        self.frames = [page(False)]
        def changed(*args, **kwargs):
            if self.client.call.called: raise k.Refused('K8S_POD_UID_CHANGED')
            return self.baseline
        with patch.object(k, 'observe', side_effect=changed):
            with self.assertRaisesRegex(k.Refused, 'POD_UID_CHANGED'):
                execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, 'progress-before')
        error = k.document(self.out/'progress-before-failure.json')
        self.assertEqual(error['sourceRefusal']['diagnostic']['failedRow']['code'], 'EVALUATOR_CLINICAL_PROGRESS_STALLED')

    def test_changed_post_freeze_input_refuses_before_source_collection(self):
        self.load.side_effect = k.Refused('K8S_RUN_CONFIG_CHANGED')
        with self.assertRaisesRegex(k.Refused, 'RUN_CONFIG_CHANGED'): self.run_phase()
        self.assertEqual(self.calls, 0)

    def test_changed_input_after_bracket_refuses_fresh_admission(self):
        state = self.run_phase()
        self.load.side_effect = k.Refused('K8S_RUN_CONFIG_CHANGED')
        with self.assertRaisesRegex(k.Refused, 'RUN_CONFIG_CHANGED'): self.fresh(state)
        self.assertEqual(k.document(self.out/'preload-convergence/fresh-readiness.json')['verdict'], 'FAIL')

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

    def cli_without_driver(self):
        self.initial_configuration();self.out.rmdir()
        with patch.object(k, 'Client', return_value=self.client),patch.object(k.candidate, 'require'), \
             patch.object(execute, 'actor', return_value={}),patch.object(execute.subprocess, 'Popen') as driver, \
             patch.object(sys, 'argv', ['adapter.py', 'load', str(self.d)]):
            try:
                k.main()
            finally:
                driver.assert_not_called()

    def test_actual_client_late_return_retained_before_original_deadline_refuses_cli(self):
        self.actual_client(delay=20)
        with self.assertRaisesRegex(k.Refused, 'K8S_OBSERVATION_DEADLINE'): self.cli_without_driver()
        sample = self.out/'preload-convergence/sample-0000'
        raw = sample/'progress.private.jsonl'
        self.assertTrue(raw.is_file(), 'bounded returned stdout was lost before typed deadline refusal')
        self.assertEqual(raw.read_bytes(), json.dumps(page()).encode()+b'\n')
        self.assertEqual(raw.stat().st_mode & 0o777, 0o600)
        response = k.document(sample/'progress-response.json')
        self.assertEqual(response['captureBoundary'], 'client-response-sink')
        self.assertEqual(response['postObservation'], 'REFUSED')
        self.assertEqual(response['sourceDecode'], 'UNMEASURED')
        self.assertTrue(k.document(sample/'progress-failure.json')['responseRetained'])
        self.assertFalse((self.out/'runid').exists())
        self.assertEqual(self.calls, 1)
        self.assertGreaterEqual(self.observe.call_count, 3)
        self.assertEqual(self.result()['failure']['code'], 'K8S_OBSERVATION_DEADLINE')

    def test_actual_client_without_sink_preserves_default_deadline_order(self):
        self.actual_client(delay=2)
        with k.observation_deadline(self.clock.now+1):
            with self.assertRaisesRegex(k.Refused, 'K8S_OBSERVATION_DEADLINE'):
                self.client.call(['inert'], read=False, output_limit=1)

    def test_actual_client_timely_bracket_still_requires_fresh_strict_read(self):
        self.frames = [page(), page(), page(False)]
        self.actual_client()
        with self.assertRaisesRegex(k.evaluator_progress.Refused, 'M7_EVALUATOR_PROGRESS_ERROR'):
            self.cli_without_driver()
        response = k.document(self.out/'progress-before-response.json')
        self.assertEqual(response['captureBoundary'], 'client-response-sink')
        self.assertEqual(response['sourceDecode'], 'REFUSED')
        self.assertTrue(response['transportSucceeded'])
        self.assertEqual(self.calls, 3)
        self.assertFalse((self.out/'runid').exists())

    def test_actual_client_nonzero_and_authorization_refusals_retain_returned_bytes(self):
        for name, stderr, code in [('exit', b'', 'K8S_OBSERVATION_LOST'),
                                   ('auth', b'EVALUATOR_SCOPE_UNSAFE', 'EVALUATOR_SCOPE_UNSAFE')]:
            with self.subTest(name=name):
                self.out = self.d/name;self.out.mkdir();self.calls = 0
                self.actual_client(returncode=1, stderr=stderr)
                with self.assertRaisesRegex(k.Refused, code):
                    execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, 'progress')
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
                with self.assertRaisesRegex(k.Refused, code):
                    execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, 'progress')
                response = k.document(self.out/'progress-response.json')
                self.assertEqual(response['captureStatus'], 'UNAVAILABLE')
                self.assertFalse(response['responseRetained'])
                self.assertEqual(response['sourceDecode'], 'UNMEASURED')

    def test_initial_actual_call_boundary_retains_refusal_before_probe_creation(self):
        # The actual retained3k point has only a generic refusal: this source
        # payload is SYNTHETIC and does not assert its missing inner cause.
        self.c.pop('preloadConvergence')
        self.initial_configuration()
        self.frames = [page(False)]
        target = self.d/'load';target.rmdir()
        with patch.object(k.candidate, 'require'), patch.object(execute, 'actor', return_value={}), \
             patch.object(execute.subprocess, 'Popen') as process:
            with self.assertRaisesRegex(k.evaluator_progress.Refused, 'M7_EVALUATOR_PROGRESS_ERROR'):
                execute.execute(self.d, self.c, self.objects, self.client, load=True)
        process.assert_not_called()
        failure = k.document(target/'progress-before-failure.json')
        self.assertTrue(failure['responseRetained'])
        self.assertTrue((target/'progress-before.private.jsonl').is_file())
        self.assertFalse((target/'runid').exists())


class Planning(unittest.TestCase):
    def test_job_bound_and_selected_load_command_do_not_extend_original_authority(self):
        now = time.time()
        c = {'deadlines':{'workUntil':iso(now+100), 'cleanupUntil':iso(now+200)}}
        expected = {'kind':'Job', 'metadata':{'name':'primer'}, 'spec':{'activeDeadlineSeconds':5}}
        actual = copy.deepcopy(expected);actual['metadata']['uid']='owned-job';actual['status']={'startTime':iso(now), 'active':1}
        client = Mock();client.get.return_value=actual
        value = preload.limits(c, {'Job/primer':expected}, client, {'objects':{'Job/primer':{'uid':'owned-job'}}}, 1800, now)
        self.assertEqual(value['clippedBy'], ['Job/primer'])
        self.assertAlmostEqual(value['effectiveSeconds'], 5, places=5)
        p = {'phases':{'preloadConvergence':{'contract':preload.shared.CONTRACT, 'seconds':1800, 'intervalSeconds':15}}}
        self.assertEqual(preload.load_command_bound(p, 10000)['seconds'], 10000)
        self.assertEqual(preload.load_command_bound(p, 100)['seconds'], 100)
        self.assertEqual(preload.load_command_bound({'phases':{}}, 10000)['seconds'], 7200)

    def test_profile_binding_records_authored_phase_and_requires_room(self):
        p = json.loads((Path(__file__).parent/'workloads/realistic-3000.json').read_text())
        p['phases']['preloadConvergence'] = {'contract':preload.shared.CONTRACT, 'seconds':1800, 'intervalSeconds':15}
        p['phases']['workSeconds'] = 10000
        value = profile.describe(p)
        self.assertEqual(value['preloadConvergence']['seconds'], 1800)
        p['phases']['workSeconds'] = 1800
        with self.assertRaisesRegex(ValueError, 'WORK_WINDOW'): profile.validate(p)

    def test_real_cli_dispatch_keeps_one_adapter_and_phase_context(self):
        code = r'''
import json,sys
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from test_preload import Preload,page,k,execute,preload
test=Preload();test.setUp()
try:
 test.initial_configuration()
 test.out.rmdir()
 test.frames=[page(),page(),page(False)]
 assert execute.k is k and preload.k is k
 original=test.client.call.side_effect
 guarded=[]
 def reply(*args,**kwargs):
  guarded.append(k._OBSERVATION_DEADLINE.get())
  assert guarded[-1] is not None
  return original(*args,**kwargs)
 test.client.call.side_effect=reply
 with patch.object(k,'Client',return_value=test.client),patch.object(k.candidate,'require'), \
      patch.object(execute,'actor',return_value={}),patch.object(execute.subprocess,'Popen') as driver:
  sys.argv=['adapter.py','load',str(test.d)]
  try:k.main()
  except k.evaluator_progress.Refused as error:
   assert str(error)=='M7_EVALUATOR_PROGRESS_ERROR'
  else:raise AssertionError('fresh unhealthy source entered')
  driver.assert_not_called()
 assert len(guarded)==3
 assert (test.d/'load/progress-before.private.jsonl').is_file()
 print(json.dumps({'sameAdapter':True,'phaseGuardedCalls':len(guarded),'ordinaryDispatched':False}))
finally:test.doCleanups()
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(Path(__file__).parent)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['sameAdapter'])


if __name__ == '__main__': unittest.main()
