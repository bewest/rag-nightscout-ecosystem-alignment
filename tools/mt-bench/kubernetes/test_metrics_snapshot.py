"""execute.metrics_snapshot: one exec retains the run's TSDB snapshot before teardown; never a stop."""
import json
from pathlib import Path
import tempfile
import unittest

import kube_adapter as k
import execute

PROMETHEUS = {('Deployment', 'prometheus'): {'kind': 'Deployment', 'metadata': {'name': 'prometheus'}}}


class Client:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def call(self, args, **options):
        self.calls.append((args, options))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)

    def test_without_the_component_nothing_is_asked(self):
        client = Client(b'x')
        self.assertIsNone(execute.metrics_snapshot(self.out, {}, {('Deployment', 'api'): {'kind': 'Deployment', 'metadata': {'name': 'api'}}}, client))
        self.assertEqual(client.calls, [])
        self.assertFalse((self.out/'metrics-snapshot.json').exists())

    def test_one_exec_retains_the_archive(self):
        client = Client(b'tar-bytes')
        receipt = execute.metrics_snapshot(self.out, {}, PROMETHEUS, client)
        self.assertEqual(len(client.calls), 1)
        args, options = client.calls[0]
        self.assertEqual(args[:5], ['exec', 'deploy/prometheus', '-c', 'prometheus', '--'])
        self.assertFalse(options['read'])
        self.assertEqual((self.out/'metrics-tsdb.tar').read_bytes(), b'tar-bytes')
        self.assertEqual(receipt['verdict'], 'OBSERVED')
        self.assertEqual(json.loads((self.out/'metrics-snapshot.json').read_text())['bytes'], 9)

    def test_a_failed_exec_is_recorded_not_raised(self):
        receipt = execute.metrics_snapshot(self.out, {}, PROMETHEUS, Client(k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED')))
        self.assertEqual((receipt['verdict'], receipt['code']), ('UNMEASURED', 'K8S_OBSERVATION_LOST'))
        self.assertFalse((self.out/'metrics-tsdb.tar').exists())


if __name__ == '__main__':
    unittest.main()
