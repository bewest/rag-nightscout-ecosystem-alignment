"""Actual strict reader/caller controls; no application or cluster actors."""
import contextlib
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import adapter as a
import contract
import discovery
import evaluator_progress as p
import preload_convergence as warm
import run_configuration as rc
import runner
from test_run_configuration import config, packet

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
R = '33333333-3333-4333-8333-333333333333'
S = '44444444-4444-4444-8444-444444444444'


def frame(code=None, acquisitions=1, runtime=R):
    rows = []
    for tenant in (A, B):
        rows.append({'tenant': tenant, 'admitted': True, 'ready': code is None,
                     'cycles': acquisitions, 'code': code, 'evaluation': {'alert': None},
                     'progress': {'generation': 1001, 'completedAcquisitions': acquisitions,
                                  'completedTimeCycles': 0, 'failedCompletions': 0,
                                  'lastCompletedAgeMs': 10 if acquisitions else None},
                     'jobs': dict.fromkeys(p.JOB_FLAGS, False), 'dueAt': None, 'dueReason': None})
    return {'selected': [A, B], 'selfOrdinal': 0, 'selfMode': 'standalone',
            'view': {'kind': 'evaluator', 'runtimeId': runtime, 'configured': {'ordinal': 0, 'mode': 'standalone'},
                     'gate': {'eligible': True, 'reason': None}, 'tenants': rows}}


def errorless_unready(running=True, acquisitions=2):
    value = frame(acquisitions=acquisitions)
    value['view']['tenants'][0]['ready'] = False
    value['view']['tenants'][0]['jobs']['running'] = running
    return value


class Clock:
    def __init__(self):
        self.now = time.time()
    def time(self): return self.now
    def monotonic_ns(self): return int(self.now*1e9)
    def sleep(self, seconds): self.now += seconds


def manifest():
    return {warm.FIELD: {'contract': warm.CONTRACT, 'seconds': 5, 'intervalSeconds': 1},
            'profile': 'pgstream-sample', 'runPurpose': 'discovery', 'completionContract': 'evaluator-work-v2',
            'discoveryAuthorization': {'executionScope': 'LOCAL_OWNED_TO_COMPLETION'},
            'pair': {'core': 'a'*40, 'deploy': 'b'*40}, 'imageId': 'sha256:'+'c'*64,
            'instrument': {'sha256': 'd'*64}, 'owner': 'e'*32, 'hostIdentity': 'f'*64,
            'tenants': 2, 'replicas': 1, 'cadence': {'loadSeconds': 5},
            'profileSelection': {}, 'settingsFingerprint': {}}


class IO:
    document = staticmethod(a.document)
    write = staticmethod(a.write)
    digest = staticmethod(a.digest)
    reserve_output = staticmethod(a.reserve_output)
    remaining_seconds = staticmethod(a.remaining_seconds)
    command_deadline = staticmethod(a.command_deadline)
    private_commands = staticmethod(a.private_commands)
    def __init__(self, values):
        self.values, self.calls, self.clock, self.index, self.lock = values, [], Clock(), 0, threading.Lock()
        self.preload_convergence = SimpleNamespace(selection=warm.selection,
            run=lambda adapter, directory, selected: warm.run(adapter, directory, selected, clock=self.clock))
    def verify(self, *args): self.calls.append('verify')
    def image(self, *args): self.calls.append('image')
    def assert_owned(self, *args): self.calls.append('owned')
    def progress_services(self, *args): return ['evaluator']
    def progress_fetch(self, *args, **kwargs):
        with self.lock:
            value = self.values[min(self.index, len(self.values)-1)]
            self.index += 1
        self.calls.append('source')
        if isinstance(value, BaseException): raise value
        return value if isinstance(value, bytes) else json.dumps(value).encode()+b'\n'
    def frozen(self, *args): self.calls.append('frozen')
    def quiet(self, *args, **kwargs): self.calls.append('quiet')
    def verify_generator(self, *args): self.calls.append('generator')
    def readiness(self, directory, selected):
        self.calls.append('normal-readiness')
        assert a._COMMAND_DEADLINE.get() is None, 'pre-load deadline leaked into normal work'
        with patch.object(a, 'progress_services', self.progress_services), \
             patch.object(a, 'progress_fetch', self.progress_fetch), patch.object(a.time, 'sleep'):
            return a.readiness(directory, selected)
    def command(self, *args):
        self.calls.append('after-readiness')
        raise RuntimeError('M7_TEST_AFTER_READINESS')


class Convergence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        a.write(self.d/'tenants.private.json', [{'id': A}, {'id': B}])
        a.write(self.d/'deploy-before-host.json', {})
        self.m = manifest()
    def run_phase(self, frames):
        io = IO(frames)
        value = warm.run(io, self.d, self.m, clock=io.clock)
        return value, io
    def saved(self): return a.document(self.d/'preload-convergence/result.json')

    def test_strict_fail_then_two_ready_views_retains_failure_and_closes_only_availability(self):
        pending = frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=1)
        pending['view']['tenants'][1]['jobs']['running'] = True
        result, io = self.run_phase([pending, frame(), frame()])
        saved = self.saved()
        self.assertEqual(saved['strictStartupVerdicts'], {'PASS': 2, 'FAIL': 1, 'UNMEASURED': 0})
        self.assertEqual(result['status'], 'CONVERGED')
        self.assertEqual(saved['readyBracket']['lastSample'], 2)
        self.assertEqual(json.loads((self.d/'preload-convergence/sample-0000/service-00.jsonl').read_bytes()), pending)
        self.assertEqual(saved['samples'][0]['diagnostic']['failedRow']['code'], 'EVALUATOR_CLINICAL_PROGRESS_STALLED')
        self.assertEqual(saved['capacityAcceptance'], 'NOT_GRANTED')
        self.assertNotIn('normal-readiness', io.calls)
        self.assertIsNone(a._COMMAND_DEADLINE.get())

    def test_already_ready_requires_two_complete_credited_views(self):
        result, _ = self.run_phase([frame(), frame()])
        self.assertEqual(result['readyBracket']['firstSample'], 0)
        self.assertEqual(result['readyBracket']['lastSample'], 1)
        self.assertEqual(result['readyBracket']['availability']['availability']['classifications']['READY'], 4)

    def test_errorless_source_transition_keeps_strict_failure_before_credited_ready_views(self):
        for running in (True, False):
            for acquisitions in (0, 2):
                with self.subTest(running=running, acquisitions=acquisitions), tempfile.TemporaryDirectory() as area:
                    d = Path(area);a.write(d/'tenants.private.json', [{'id': A}, {'id': B}])
                    positive = frame(acquisitions=max(1, acquisitions))
                    io = IO([errorless_unready(running, acquisitions), positive, positive])
                    warm.run(io, d, self.m, clock=io.clock)
                    saved = a.document(d/'preload-convergence/result.json')
                    self.assertEqual([sample['verdict'] for sample in saved['samples']], ['FAIL', 'PASS', 'PASS'])
                    self.assertIsNone(saved['samples'][0]['diagnostic']['failedRow']['code'])

    def test_partly_warm_roster_is_a_signal_and_reaches_traffic(self):
        """preload-is-a-signal: an unconverged roster is recorded, never refused."""
        for running in (True, False):
            with self.subTest(running=running), tempfile.TemporaryDirectory() as area:
                d = Path(area);a.write(d/'tenants.private.json', [{'id': A}, {'id': B}])
                io = IO([errorless_unready(running=running)])
                result = warm.run(io, d, self.m, clock=io.clock)
                saved = a.document(d/'preload-convergence/result.json')
                self.assertEqual((result['status'], saved['status']), ('NOT_CONVERGED', 'NOT_CONVERGED'))
                self.assertFalse(saved['signal']['converged'])
                self.assertIsNone(saved['signal']['convergenceSeconds'])
                self.assertEqual(saved['signal']['lastCohortCompletion']['owners'], 2)
                self.assertNotIn('failure', saved)

    def test_partly_warm_then_converged_records_the_convergence_time(self):
        pending = frame('EVALUATOR_STARTING', acquisitions=0)
        result, _ = self.run_phase([pending, pending, frame(), frame()])
        self.assertEqual(result['status'], 'CONVERGED')
        self.assertTrue(result['signal']['converged'])
        self.assertAlmostEqual(result['signal']['convergenceSeconds'], 3.0, delta=0.5)

    def test_signal_still_refuses_source_corruption(self):
        """Only the not-yet-warm outcome is a signal. Owner and counter checks stay hard."""
        with self.assertRaisesRegex(RuntimeError, 'RUNTIME_CHANGED'):
            self.run_phase([frame(runtime=R), frame(runtime=S)])

    def test_opt_in_all_tenant_readiness_still_refuses_an_unconverged_roster(self):
        self.m[warm.FIELD]['readiness'] = warm.STRICT
        for running in (True, False):
            with self.subTest(running=running), tempfile.TemporaryDirectory() as area:
                d = Path(area);a.write(d/'tenants.private.json', [{'id': A}, {'id': B}])
                io = IO([errorless_unready(running=running)])
                with self.assertRaisesRegex(RuntimeError, 'CONVERGENCE_EXPIRED'):
                    warm.run(io, d, self.m, clock=io.clock)
                saved = a.document(d/'preload-convergence/result.json')
                self.assertTrue(all(sample['verdict'] == 'FAIL' for sample in saved['samples']))

    def test_permanent_poison_after_errorless_unready_still_refuses_first_snapshot(self):
        value = errorless_unready()
        value['view']['tenants'][1].update(ready=False, code='EVALUATOR_CONFIG_REFUSED')
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_REFUSAL'):
            self.run_phase([value, frame(acquisitions=2), frame(acquisitions=2)])
        self.assertEqual(len(self.saved()['samples']), 1)
        self.assertEqual(self.saved()['failure']['diagnostic']['tenant'], B)

    def test_first_release_zero_credit_and_starting_are_not_ready(self):
        self.run_phase([frame('EVALUATOR_STARTING', acquisitions=0), frame(acquisitions=0), frame(), frame()])
        self.assertEqual([v['verdict'] for v in self.saved()['samples']], ['UNMEASURED', 'UNMEASURED', 'PASS', 'PASS'])

    def test_persistent_pending_input_expires_phase_without_ordinary_or_threshold_change(self):
        self.m[warm.FIELD]['readiness'] = warm.STRICT
        io = IO([frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=0)])
        with self.assertRaisesRegex(RuntimeError, 'CONVERGENCE_EXPIRED'):
            warm.run(io, self.d, self.m, clock=io.clock)
        saved = self.saved()
        self.assertEqual(saved['status'], 'REFUSED')
        self.assertTrue(all(value['verdict'] == 'FAIL' for value in saved['samples']))
        self.assertEqual(self.m[warm.FIELD]['seconds'], 5)

    def test_poison_after_first_pending_row_refuses_immediately(self):
        bad = frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=0)
        bad['view']['tenants'][1]['code'] = 'EVALUATOR_ACQUISITION_REFUSED'
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_REFUSAL'):
            self.run_phase([bad, frame(), frame()])
        self.assertEqual(len(self.saved()['samples']), 1)
        self.assertEqual(self.saved()['failure']['diagnostic']['tenant'], B)
        self.assertEqual(self.saved()['failure']['diagnostic']['code'], 'EVALUATOR_ACQUISITION_REFUSED')

    def test_failed_evaluation_behind_first_pending_row_refuses_immediately(self):
        bad = frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=0)
        bad['view']['tenants'][1]['progress']['failedCompletions'] = 1
        with self.assertRaisesRegex(RuntimeError, 'EVALUATION_FAILURE'):
            self.run_phase([bad, frame(), frame()])
        self.assertEqual(len(self.saved()['samples']), 1)

    def test_runtime_reset_and_counter_rewind_are_permanent(self):
        for field in ('runtime', 'counter', 'generation'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as area:
                d = Path(area);a.write(d/'tenants.private.json', [{'id': A}, {'id': B}])
                values = [frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=1),
                          frame(runtime=S) if field == 'runtime' else frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=0)]
                if field == 'generation':
                    values[1] = frame('EVALUATOR_CLINICAL_PROGRESS_STALLED', acquisitions=1)
                    values[1]['view']['tenants'][0]['progress']['generation'] = 1
                io = IO(values)
                with self.assertRaisesRegex(RuntimeError, 'RUNTIME_CHANGED' if field == 'runtime' else 'COUNTER_REWOUND'):
                    warm.run(io, d, self.m, clock=io.clock)

    def test_incomplete_and_unknown_source_errors_do_not_loop(self):
        with self.assertRaisesRegex(RuntimeError, 'INCOMPLETE_SOURCE'):
            self.run_phase([p.Refused('M7_EVALUATOR_PROGRESS_UNAVAILABLE')])
        self.assertEqual(len(self.saved()['samples']), 1)
        self.assertEqual(self.saved()['samples'][0]['verdict'], 'UNMEASURED')

    def test_wrong_owner_refuses_and_raw_malformed_snapshot_is_preserved(self):
        bad = frame();bad['view']['tenants'][0]['admitted'] = False
        with self.assertRaisesRegex(RuntimeError, 'FOREIGN_READY'):
            self.run_phase([bad])

    def test_actual_resource_ownership_check_runs_before_observation(self):
        io = IO([frame()])
        io.assert_owned = a.assert_owned
        wrong = {'Config': {'Labels': {a.OWNER: 'foreign'}}}
        with patch.object(a, 'resources', return_value=[wrong]):
            with self.assertRaisesRegex(RuntimeError, 'M7_RESOURCE_NOT_OWNED'):
                warm.run(io, self.d, self.m, clock=io.clock)
        self.assertEqual(io.index, 0)
        self.assertEqual(self.saved()['failure']['code'], 'M7_RESOURCE_NOT_OWNED')

    def test_malformed_raw_is_retained_before_terminal_contract_refusal(self):
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_CONTRACT'):
            self.run_phase([b'{not json}\n'])
        self.assertEqual((self.d/'preload-convergence/sample-0000/service-00.jsonl').read_bytes(), b'{not json}\n')
        self.assertTrue((self.d/'preload-convergence/sample-0000/sample.json').is_file())

    def test_normal_caller_runs_unchanged_fresh_readiness_and_rejects_a_new_failure(self):
        io = IO([frame('EVALUATOR_CLINICAL_PROGRESS_STALLED'), frame(), frame(),
                 frame('EVALUATOR_CLINICAL_PROGRESS_STALLED')])
        with self.assertRaisesRegex(p.Refused, 'PROGRESS_ERROR'):
            discovery._run_discovery(io, self.d, self.m, 'never-launched')
        self.assertIn('normal-readiness', io.calls)
        self.assertNotIn('after-readiness', io.calls)
        self.assertEqual(self.saved()['status'], 'CONVERGED')
        self.assertEqual(a.document(self.d/'runtime-readiness.json')['verdict'], 'FAIL')

    def test_fresh_normal_readiness_keeps_existing_null_code_unavailable_semantics(self):
        io = IO([errorless_unready(), frame(acquisitions=2), frame(acquisitions=2), errorless_unready()])
        with self.assertRaisesRegex(RuntimeError, 'M7_TEST_AFTER_READINESS'):
            discovery._run_discovery(io, self.d, self.m, 'never-launched')
        self.assertEqual(self.saved()['status'], 'CONVERGED')
        # This is the existing independent discovery gate, not a pre-load
        # strict view. Preserve its UNMEASURED result rather than inventing a
        # new normal-readiness restriction for this source transition.
        self.assertEqual(a.document(self.d/'runtime-readiness.json')['verdict'], 'UNMEASURED')
        self.assertIn('after-readiness', io.calls)

    def test_baseline_without_selection_still_refuses_first_strict_failure(self):
        self.m.pop(warm.FIELD)
        io = IO([frame('EVALUATOR_CLINICAL_PROGRESS_STALLED')])
        with self.assertRaisesRegex(p.Refused, 'PROGRESS_ERROR'):
            discovery._run_discovery(io, self.d, self.m, 'never-launched')
        self.assertFalse((self.d/'preload-convergence').exists())
        self.assertEqual(io.index, 1)


class Configuration(unittest.TestCase):
    def setUp(self):
        self.pin = patch.object(a, 'instrument', return_value={'sha256': 'd'*64})
        self.pin.start();self.addCleanup(self.pin.stop)
    def selected(self):
        value = config();value.update(tier='discovery', workSeconds=None)
        value['prepare'].update({'setup-seconds': 900, 'drain-seconds': 900,
                                'completion-contract': 'evaluator-work-v2', 'preload-convergence-seconds': 900,
                                'preload-convergence-interval-seconds': 15})
        return value
    def test_selected_phase_is_configuration_and_receipt_bound_to_local_owner_mode(self):
        value = self.selected()
        effective = rc.resolve(value)['configuration']
        self.assertEqual(effective[warm.FIELD], {'contract': warm.CONTRACT, 'seconds': 900, 'intervalSeconds': 15})
        manifest, receipt = packet(value)
        receipt['executionScope'] = 'LOCAL_OWNED_TO_COMPLETION'
        contract.discovery_authorization(manifest, receipt)
        original = copy.deepcopy(manifest['runConfiguration'])
        manifest['runConfiguration'] = copy.deepcopy(original)
        manifest['runConfiguration'][warm.FIELD]['seconds'] = 901
        receipt['configurationSha256'] = rc.sha(manifest['runConfiguration'])
        with self.assertRaisesRegex(RuntimeError, 'CONFIGURATION_MISMATCH'):
            contract.discovery_authorization(manifest, receipt)
        manifest['runConfiguration'] = original
        receipt['configurationSha256'] = rc.sha(original)
        receipt['executionScope'] = 'wrong'
        with self.assertRaisesRegex(RuntimeError, 'OWNED_TO_COMPLETION_RECEIPT_REQUIRED'):
            contract.discovery_authorization(manifest, receipt)
        with self.assertRaisesRegex(RuntimeError, 'OWNED_TO_COMPLETION_RECEIPT_REQUIRED'):
            contract.discovery_authorization(manifest, {'version': 1})
    def test_opt_in_readiness_flag_is_configuration_and_default_is_signal(self):
        value = self.selected()
        self.assertNotIn('readiness', rc.resolve(value)['configuration'][warm.FIELD])
        value['prepare']['preload-readiness'] = 'require-all'
        self.assertEqual(rc.resolve(value)['configuration'][warm.FIELD]['readiness'], 'require-all')
        value = self.selected();del value['prepare']['preload-convergence-seconds'], value['prepare']['preload-convergence-interval-seconds']
        value['prepare']['preload-readiness'] = 'require-all'
        with self.assertRaisesRegex(RuntimeError, 'PRELOAD_SECONDS_REQUIRED'):
            rc.resolve(value)
    def test_bounded_old_run_and_invalid_phase_are_rejected_before_preparation(self):
        value = self.selected();value['workSeconds'] = 7200
        with self.assertRaisesRegex(RuntimeError, 'LOCAL_OWNED_TO_COMPLETION_REQUIRED'):
            rc.resolve(value)
        value = self.selected();value['prepare']['preload-convergence-interval-seconds'] = 900
        with self.assertRaisesRegex(RuntimeError, 'PRELOAD_WINDOW'):
            rc.resolve(value)


if __name__ == '__main__':
    unittest.main()
