"""python3 -B -m unittest discover -s tools/mt-bench/kubernetes/connectors -p 'test_*.py'"""
import copy
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'workloads'))
import connectors  # noqa: E402
import profile as workload_profile  # noqa: E402


def roster(n):
    return [{'id': '3000%04x-3333-4333-8333-%012x' % (i, i), 'host': 't%d.example.test' % i, 'dataToken': 'tok%d' % i} for i in range(n)]


class Selection(unittest.TestCase):
    def test_share_takes_the_roster_tail_outside_the_ordinary_roster(self):
        pop = {'provisionedTenants': 20, 'ordinaryRosterTenants': 15, 'connectorShare': 0.25}
        chosen = connectors.select(roster(20), pop)
        self.assertEqual([r['host'] for r in chosen], ['t%d.example.test' % i for i in range(15, 20)])
        self.assertEqual([r['site'] for r in chosen], ['s0', 's1', 's2', 's3', 's4'])
        self.assertEqual(connectors.count(1000, 0.10), 100)
        self.assertEqual(connectors.select(roster(4), {'provisionedTenants': 4, 'ordinaryRosterTenants': 4}), [])

    def test_connector_tenants_that_also_receive_uploader_writes_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            connectors.validate({'provisionedTenants': 20, 'ordinaryRosterTenants': 16, 'connectorShare': 0.25})
        with self.assertRaisesRegex(ValueError, 'SHARE'):
            connectors.validate({'provisionedTenants': 20, 'ordinaryRosterTenants': 10, 'connectorShare': 1.5})

    def test_inputs_and_manifests(self):
        chosen = connectors.select(roster(8), {'provisionedTenants': 8, 'ordinaryRosterTenants': 6, 'connectorShare': 0.25})
        tokens = connectors.sites(chosen, token=iter(['a' * 32, 'b' * 32]).__next__)
        entry = connectors.entry_input(chosen, tokens)
        self.assertEqual(entry['tenants'][1], {'id': chosen[1]['id'], 'endpoint': 'http://nightscout-upstream:1337/s/s1', 'sourceCredential': 'b' * 32})
        self.assertEqual(entry['collections'], ['entries', 'treatments', 'devicestatus'])
        score = connectors.score_input(chosen, 123)
        self.assertEqual(score['tenants'][0]['token'], 'tok6')
        objs = connectors.manifests('lanev-vcpool', 'localhost:14100/app@sha256:' + '0' * 64, 123, {'nightscout.org/run-id': 'r1'})
        kinds = sorted((o['kind'], o['metadata']['name']) for o in objs)
        self.assertEqual(kinds, [('ConfigMap', 'connector-scripts'), ('Deployment', 'connector-score'), ('Deployment', 'nightscout-upstream'),
                                 ('NetworkPolicy', 'upstream-from-vcpool'), ('Service', 'nightscout-upstream')])
        policy = next(o for o in objs if o['kind'] == 'NetworkPolicy')
        self.assertEqual([f['podSelector']['matchLabels']['app.kubernetes.io/component'] for f in policy['spec']['ingress'][0]['from']], ['vcpool', 'operator'])
        self.assertTrue(all(o['metadata']['labels']['nightscout.org/run-id'] == 'r1' for o in objs))


class Profile(unittest.TestCase):
    def base(self):
        p = json.loads((HERE.parent / 'workloads' / 'small.json').read_text())
        p['population'].update(provisionedTenants=4, ordinaryRosterTenants=3)
        return p

    def test_profile_accepts_a_share_outside_the_ordinary_roster_and_describes_it(self):
        p = self.base(); p['population']['connectorShare'] = 0.25
        workload_profile.validate(p)
        self.assertEqual(workload_profile.describe(p)['connectorTenants'], 1)
        self.assertNotIn('connectorTenants', workload_profile.describe(self.base()))

    def test_profile_refuses_connectors_on_uploader_tenants(self):
        p = self.base(); p['population']['connectorShare'] = 0.5
        with self.assertRaisesRegex(ValueError, 'K8S_LOAD_CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            workload_profile.validate(p)


if __name__ == '__main__':
    unittest.main()
