"""Phase rotation only retires the predecessor's captured Kubernetes writers."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import phase_actors as actors


class ActorRotation(unittest.TestCase):
    def setUp(self):
        self.ids = {'namespace': 'namespace-id', 'pvc': 'claim-id', 'secret': 'secret-1', 'job': 'job-1'}
        self.job = {'kind': 'Job', 'metadata': {'name': 'k6', 'namespace': 'rehearsal',
                    'labels': {'nightscout.org/run-id': 'trial'}}, 'spec': {'suspend': True}}
        self.storage = actors.storage_identity(self.run_api, 'rehearsal', 'namespace-id', 'trial', 'pg')
        self.first = {**self.storage, 'inputSecretUid': 'secret-1', 'jobUid': 'job-1'}
        self.deleted = []

    def run_api(self, args, *, input=None):
        if args[0] == 'get':
            uid = self.ids.get(args[1])
            value = (uid + ' trial').encode() if uid else b''
        elif args[0] == 'delete':
            kind = 'job' if args[2].endswith('/jobs/k6') else 'secret'
            options = json.loads(input)
            self.assertEqual(options['preconditions'], {'uid': self.ids.pop(kind)})
            self.assertEqual(options['propagationPolicy'], 'Foreground')
            self.deleted.append(kind)
            value = b''
        else:
            self.assertEqual(json.loads(input), self.job)
            self.ids['job'] = 'job-2'
            value = b'job-2'
        return SimpleNamespace(stdout=value)

    def rotate(self):
        return actors.new_job(self.run_api, 'rehearsal', 'trial', self.storage, self.first, self.job, 9999999999)

    def test_only_retires_the_captured_job_and_secret(self):
        self.assertEqual(self.rotate(), 'job-2')
        self.assertEqual(self.deleted, ['job', 'secret'])
        self.assertEqual(self.ids['namespace'], self.storage['namespaceUid'])
        self.assertEqual(self.ids['pvc'], self.storage['postgresClaimUid'])

    def test_replaced_secret_or_claim_refuses_before_any_mutation(self):
        self.ids['secret'] = 'replacement'
        with self.assertRaisesRegex(RuntimeError, 'POINT_ACTOR_CHANGED'):
            self.rotate()
        self.assertEqual(self.deleted, [])
        self.first['postgresClaimUid'] = 'different-restore'
        with self.assertRaisesRegex(RuntimeError, 'POINT_RESTORE_CHANGED'):
            self.rotate()
        self.assertEqual(self.deleted, [])

    def test_requires_measured_stage_and_experiment_for_failure_to_advance(self):
        with tempfile.TemporaryDirectory() as scratch:
            packet = Path(scratch)
            result = packet/'experiment/result.json'
            result.parent.mkdir()
            result.write_text('{"verdict":"FAIL"}')
            self.assertFalse(actors.scored_failure(packet))
            stage = packet/'load/result.json'
            stage.parent.mkdir()
            stage.write_text('{"verdict":"UNMEASURED"}')
            self.assertFalse(actors.scored_failure(packet))
            stage.write_text('{"verdict":"FAIL"}')
            self.assertTrue(actors.scored_failure(packet))
