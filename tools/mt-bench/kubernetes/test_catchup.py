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
        check = calls.enter_context(patch.object(catchup.clinical_sql, 'observe', return_value=('postgres-pod', 'postgres')))
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
        check.side_effect = [('postgres-pod', 'postgres'), k.Refused('K8S_POD_UID_CHANGED', 'UNMEASURED')]
        with self.assertRaisesRegex(k.Refused, 'POD_UID_CHANGED'):
            fetch('SELECT 1', 1)
        sql.assert_called_once()

    def test_unrelated_restart_and_owned_postgres_discontinuity(self):
        c, inventory, rendered, client = fixture()
        c['completion'] = {'binding':'synthetic'}
        objects = k.validate(c, inventory, rendered)
        baseline = k.observe(c, objects, client)
        with patch.object(k, 'active_baseline', return_value=baseline), patch.object(k, 'postgres_read', return_value='sample') as sql:
            sample = catchup.observer(None, c, objects, client, 'owned', [A, B]).fetch
            statuses = {s['name']:s for p in client.pods for s in p['status']['containerStatuses']}
            statuses['api']['containerID'] = 'replacement-api'
            self.assertEqual(sample('SELECT 1', 5), 'sample')
            original = statuses['postgres']['containerID']
            sql.side_effect = lambda *_, **__: statuses['postgres'].update(containerID='replacement-postgres')
            with self.assertRaisesRegex(k.Refused, 'CONTAINER_INCARNATION_CHANGED') as stopped:
                sample('SELECT 1', 5)
            self.assertEqual(stopped.exception.verdict, 'UNMEASURED')
            statuses['postgres']['containerID'] = original
            sql.side_effect = None
            self.assertEqual(sample('SELECT 1', 5), 'sample')
            postgres = next(p for p in client.pods if p['status']['containerStatuses'][0]['name'] == 'postgres')
            postgres['metadata']['labels'][c['ownerLabel']] = 'peer'
            with self.assertRaisesRegex(k.Refused, 'PEER_RESOURCE_REFUSED') as foreign:
                sample('SELECT 1', 5)
            self.assertEqual(foreign.exception.verdict, 'FAIL')
            self.assertEqual(sql.call_count, 3)

    def test_failed_read_still_checks_identity(self):
        fetch, check, _ = self.reader(k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED'))
        with self.assertRaisesRegex(k.Refused, 'OBSERVATION_LOST'):
            fetch('SELECT 1', 1)
        self.assertEqual(check.call_count, 2)
