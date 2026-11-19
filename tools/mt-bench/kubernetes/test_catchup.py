"""Controls for the read-only Kubernetes transport used by the accepted-input observer."""
from contextlib import ExitStack
import sys
import time
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
        client = object()
        scope = {'namespace': {'uid': 'private-synthetic'}}
        calls = ExitStack()
        self.addCleanup(calls.close)
        observer = Mock()
        calls.enter_context(patch.dict(sys.modules, {'accepted_inputs': SimpleNamespace(Observer=observer)}))
        calls.enter_context(patch.object(k, 'active_baseline', return_value=scope))
        check = calls.enter_context(patch.object(k, 'observe', return_value=scope))
        calls.enter_context(patch.object(k, 'selected_pod', return_value=('postgres-pod', 'postgres')))
        sql = calls.enter_context(patch.object(k, 'postgres_read', side_effect=read))
        catchup.observer(None, c, {}, client, 'accepted-input-test', [A, B])
        args = observer.call_args.kwargs
        self.assertEqual((args['run_id'], args['ids'], args['config']), ('accepted-input-test', [A, B], c['completion']))
        return args['fetch'], check, sql

    def test_sql_reads_owned_postgres_within_both_deadlines(self):
        ticks = []
        def read(*_, **options):
            ticks.append(k._OBSERVATION_DEADLINE.get())
            self.assertGreater(options['timeout'], 0)
            self.assertLessEqual(options['timeout'], 1)
            return '{"tenant":"synthetic"}\n'
        fetch, check, sql = self.reader(read)
        self.assertEqual(fetch('SELECT 1', 1), '{"tenant":"synthetic"}\n')
        self.assertEqual(check.call_count, 2)
        self.assertEqual(check.call_args_list[0], check.call_args_list[1])
        self.assertIn('SELECT 1', sql.call_args.args[3])
        self.assertIn('SET LOCAL statement_timeout=', sql.call_args.args[3])
        self.assertLessEqual(ticks[0], time.time() + 1)
        self.assertIsNone(k._OBSERVATION_DEADLINE.get())

    def test_changed_source_fails_after_sql(self):
        fetch, check, sql = self.reader(lambda *_, **__: '')
        check.side_effect = [{}, k.Refused('K8S_POD_UID_CHANGED', 'FAIL')]
        with self.assertRaisesRegex(k.Refused, 'POD_UID_CHANGED'):
            fetch('SELECT 1', 1)
        sql.assert_called_once()

    def test_failed_read_still_checks_identity(self):
        fetch, check, _ = self.reader(k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED'))
        with self.assertRaisesRegex(k.Refused, 'OBSERVATION_LOST'):
            fetch('SELECT 1', 1)
        self.assertEqual(check.call_count, 2)
