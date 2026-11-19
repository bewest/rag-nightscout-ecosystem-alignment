"""Exercise the lifecycle ordering against synthetic Kubernetes Job replies."""
import ast
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

from kube_adapter import candidate


class VerifiedServing(unittest.TestCase):
    def attempt(self, condition, *, missing_proof=False, slow_primer=False, slow_serving=False):
        source = Path(__file__).with_name('lifecycle.py')
        functions = [node for node in ast.parse(source.read_text()).body
                     if isinstance(node, ast.FunctionDef) and node.name in ('start_serving', 'verify_database')]
        calls, records = [], {}
        job = {'metadata': {'uid': 'verify-job'}, 'spec': {'activeDeadlineSeconds': 900},
               'status': {'conditions': [{'type': condition, 'status': 'True'}]}}
        exit_code = 0 if condition == 'Complete' else 1
        container = {'name': 'done', 'containerID': 'containerd://verify',
                     'state': {'terminated': {'exitCode': exit_code}}}
        pod = {'metadata': {'name': 'verification-k', 'uid': 'verify-pod',
                            'labels': {'nightscout.org/run-id': 'run'},
                            'ownerReferences': [{'controller': True, 'uid': 'verify-job'}]},
               'status': {'containerStatuses': [container]}}
        proof = {'version': 1, 'status': 'verified', 'credentialBoundary': 'admin-private-api',
                 'fixture': {'namespace': 'ns', 'runId': 'run'}, 'nativeSelectionSha256': 'a'*64,
                 'selectionSha256': 'b'*64, 'nativeGeneration': 'synthetic',
                 'nativeSource': {'system_id': '1', 'timeline': 1,
                                  'database': 'nightscout_compose_test', 'slot': 'nsdemo_pgstream'},
                 'roles': [{'role': role, 'generation': 'c'*64} for role in candidate.ROLES]}

        @contextmanager
        def window(*_):
            yield 60

        def command(argv, **_):
            if 'wait' in argv:
                calls.append('job-watch')
                if condition != 'Complete':
                    raise subprocess.TimeoutExpired(argv, 60)
                return b''
            self.assertIn('logs', argv)
            calls.append('proof-log')
            return json.dumps({} if missing_proof else proof).encode()

        def ready(*_):
            calls.append('primer-ready')
            if slow_primer:
                raise RuntimeError('READY_DEADLINE_primer')

        def serving_ready(stage):
            calls.append('ready:'+stage)
            if slow_serving:
                raise RuntimeError('READY_DEADLINE_serving')

        scope = dict(cfg={'bindingDirectory': '/synthetic'}, read=lambda _: {'platformVerification': 'startup-v3'},
                     Path=Path, candidate=candidate, subprocess=subprocess, startup_window=window,
                     time=SimpleNamespace(time=lambda: 0), rpc=['kubectl'], tool=Path('/synthetic/bin'),
                     ctx='synthetic', ns='ns', rid='run', owned=lambda: None, step=lambda _: None,
                     get=lambda *_: job, pods=lambda _: [pod], require_pod_uid=lambda *_: None,
                     summary=lambda _: {'containers': [container]}, failure_codes=lambda *_: {'codes': ['SYNTHETIC']},
                     put=lambda name, value: records.update({name: value}), command=command,
                     install=lambda stage: calls.append('install:'+stage),
                     release_job=lambda name: calls.append('release:'+name) or job,
                     workload_ready=serving_ready,
                     waits={'platformVerifySeconds': 60, 'primerReadySeconds': 90}, ready=ready)
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), scope)
        return lambda: scope['start_serving'](True), calls, records

    def test_failed_job_and_missing_proof_block_serving_then_restore(self):
        for condition, missing_proof, code in (
            ('Failed', False, 'SOURCE_PLATFORM_VERIFICATION_FAILED'),
            ('Complete', True, 'CANDIDATE_ADMIN_PROOF_REQUIRED'),
        ):
            with self.subTest(condition=condition, missing_proof=missing_proof):
                launch, calls, records = self.attempt(condition, missing_proof=missing_proof)
                with self.assertRaisesRegex(RuntimeError, code):
                    launch()
                self.assertNotIn('install:serving', calls)
                self.assertNotIn('release:primer', calls)
                if condition == 'Failed':
                    self.assertEqual(records['platform-failure.json']['logs'], [{'codes': ['SYNTHETIC']}])
        launch, calls, records = self.attempt('Complete')
        launch()
        self.assertEqual(calls.count('proof-log'), 1)
        self.assertEqual(records['platform-verification.json']['proof']['status'], 'verified')
        self.assertLess(calls.index('proof-log'), calls.index('install:serving'))
        self.assertLess(calls.index('install:serving'), calls.index('release:primer'))
        self.assertLess(calls.index('ready:serving'), calls.index('release:primer'))

    def test_unready_serving_blocks_standalone_primer_then_restore(self):
        launch, calls, _ = self.attempt('Complete', slow_serving=True)
        with self.assertRaisesRegex(RuntimeError, 'READY_DEADLINE_serving'):
            launch()
        self.assertNotIn('release:primer', calls)
        launch, calls, _ = self.attempt('Complete')
        launch()
        self.assertLess(calls.index('ready:serving'), calls.index('release:primer'))

    def test_slow_primer_does_not_hold_serving_then_restore(self):
        launch, calls, _ = self.attempt('Complete', slow_primer=True)
        with self.assertRaisesRegex(RuntimeError, 'READY_DEADLINE_primer'):
            launch()
        self.assertLess(calls.index('ready:serving'), calls.index('primer-ready'))
        restored, calls, _ = self.attempt('Complete')
        restored()
        self.assertLess(calls.index('ready:serving'), calls.index('release:primer'))
        self.assertEqual(calls[-1], 'primer-ready')
