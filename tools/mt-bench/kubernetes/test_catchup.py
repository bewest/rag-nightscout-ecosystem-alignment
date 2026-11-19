"""The Kubernetes transport for the shared accepted-input collector."""
from contextlib import ExitStack
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import catchup
import kube_adapter as k
from test_adapter import A, B, fixture


class AcceptedInputTransport(unittest.TestCase):
    def reader(self, read):
        c, _, _, _ = fixture()
        c['completion'] = {'binding': 'synthetic'}
        calls = ExitStack()
        self.addCleanup(calls.close)
        observer = Mock()
        calls.enter_context(patch.dict(sys.modules, {'accepted_inputs': SimpleNamespace(Observer=observer)}))
        calls.enter_context(patch.object(k, 'active_baseline', return_value={}))
        locate = calls.enter_context(patch.object(catchup.clinical_sql, 'observe', return_value=('postgres-pod', 'postgres')))
        sql = calls.enter_context(patch.object(k, 'postgres_read', side_effect=read))
        catchup.observer(None, c, {}, object(), 'accepted-input-test', [A, B])
        args = observer.call_args.kwargs
        self.assertEqual((args['run_id'], args['ids'], args['config']), ('accepted-input-test', [A, B], c['completion']))
        return args['fetch'], locate, sql

    def test_read_is_bounded_by_the_request_and_the_work_deadline(self):
        fetch, locate, sql = self.reader(lambda *_, **options: '{"tenant":"synthetic"}\n')
        self.assertEqual(fetch('SELECT 1', 1), '{"tenant":"synthetic"}\n')
        self.assertEqual(locate.call_count, 1)
        self.assertIn('SET LOCAL statement_timeout=', sql.call_args.args[3])
        self.assertLessEqual(sql.call_args.kwargs['timeout'], 1)

    def test_postgres_restart_is_not_refused_by_the_reader(self):
        # Datastore health is judged from the Pod bookends by assessor.py.
        fetch, locate, _ = self.reader(lambda *_, **__: 'sample')
        locate.side_effect = [('postgres-0', 'postgres'), ('postgres-0', 'postgres')]
        self.assertEqual(fetch('SELECT 1', 1), 'sample')
        self.assertEqual(fetch('SELECT 1', 1), 'sample')

    def test_failed_read_propagates_to_the_collector(self):
        fetch, _, _ = self.reader(k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED'))
        with self.assertRaisesRegex(k.Refused, 'OBSERVATION_LOST'):
            fetch('SELECT 1', 1)


if __name__ == '__main__':
    unittest.main()
