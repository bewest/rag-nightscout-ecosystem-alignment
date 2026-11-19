import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import scheduler_placement as placement


class SchedulerPlacementTests(unittest.TestCase):
    def setUp(self):
        self.config = {'namespace': 'fixture', 'driver': {'node': '/tool/node'}}
        self.current = {'namespace': {'uid': 'fixture-uid'}, 'pods': {
            'api': {'uid': 'api-uid', 'workload': 'Deployment/api', 'nodeName': 'second'},
        }}
        self.requests = {'second': {'millicpus': 200, 'memoryBytes': 256, 'ephemeralBytes': 128}}
        self.pods = [
            {'metadata': {'uid': 'api-uid', 'namespace': 'fixture'}, 'status': {'phase': 'Running'},
             'spec': {'nodeName': 'second', 'containers': [
                 {'resources': {'requests': {'cpu': '200m'}}, 'env': [{'name': 'private'}]},
             ]}},
            {'metadata': {'uid': 'peer-uid', 'namespace': 'peer'}, 'status': {'phase': 'Running'},
             'spec': {'nodeName': 'second', 'containers': [{'resources': {'requests': {'cpu': '400m'}}}]}},
        ]

    def check(self, fits):
        responses = iter([json.dumps({'items': self.pods}).encode(), b'{"items":[]}',
                          b'second 200m 5% 1000Mi 15%\n'])
        client = SimpleNamespace(call=lambda _: next(responses))
        with (patch.object(placement.k, 'load', return_value=('packet', self.config, {})),
              patch.object(placement.k, 'active_baseline', return_value=self.current),
              patch.object(placement.k, 'observe', return_value=self.current),
              patch.object(placement.matrix, 'identity'),
              patch.object(placement.matrix, 'node_requests', return_value=self.requests),
              patch.object(placement.k, 'deadline', return_value=5),
              patch.object(placement.subprocess, 'run') as run):
            run.return_value.stdout = json.dumps([{'node': 'second', 'fits': fits}])
            result = placement.confirm('packet', '/binding', client)
        request = json.loads(run.call_args.kwargs['input'])
        self.assertEqual(result['incrementalRequests'], {'cpu': 0, 'memory': 0})
        self.assertEqual(result['nodeCeilings'], self.requests)
        self.assertEqual(result['pods']['api']['nodeName'], 'second')
        self.assertEqual(len(request['pods']['items']), 2)
        self.assertNotIn('env', request['pods']['items'][0]['spec']['containers'][0])
        self.assertEqual(result['fits'], fits)

    def test_already_bound_fixture_and_peers_share_one_census(self):
        self.check(True)

    def test_fit_refusal_is_retained(self):
        self.check(False)

    def test_missing_actual_node_assignment_cannot_pass(self):
        self.pods[0]['spec']['nodeName'] = 'first'
        with self.assertRaisesRegex(placement.k.Refused, 'SCHEDULER_POD_CENSUS_CHANGED'):
            self.check(True)
