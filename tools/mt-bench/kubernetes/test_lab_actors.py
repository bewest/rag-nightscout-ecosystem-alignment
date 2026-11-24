"""The namespace census admits the vcpool connector lab actors by label and controller name; any other
unrendered controller is still refused (POD_CONTROLLER)."""
import copy
import unittest

import kube_adapter as k
from test_application_topology import separate_fixture


def add_deployment(client, c, name, labels):
    meta = {'name': name, 'namespace': c['namespace'], 'uid': 'uid-' + name, 'resourceVersion': '10',
            'labels': {c['ownerLabel']: c['runId'], **labels}}
    client.objects['Deployment/' + name] = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': meta, 'spec': {}}
    rs = {'apiVersion': 'apps/v1', 'kind': 'ReplicaSet', 'metadata': {**copy.deepcopy(meta), 'name': name + '-rs', 'uid': name + '-rs',
          'ownerReferences': [{'kind': 'Deployment', 'name': name, 'uid': meta['uid'], 'controller': True}]}}
    client.replicas.append(rs)
    client.pods.append({'kind': 'Pod', 'apiVersion': 'v1', 'metadata': {**copy.deepcopy(meta), 'name': name + '-pod', 'uid': name + '-pod',
                        'ownerReferences': [{'kind': 'ReplicaSet', 'name': name + '-rs', 'uid': name + '-rs', 'controller': True}]},
                        'spec': {'nodeName': 'synthetic-worker', 'containers': [{'name': 'x', 'resources': {}}]},
                        'status': {'phase': 'Running'}})


class LabActors(unittest.TestCase):
    def setUp(self):
        self.c, self.inventory, self.rendered, self.client = separate_fixture()
        self.objects = k.validate(self.c, self.inventory, self.rendered)

    def test_connector_lab_actors_are_admitted_by_label_and_name(self):
        self.c['connectors'] = {'share': 0.25}
        for name in ('nightscout-upstream', 'connector-score'):
            add_deployment(self.client, self.c, name, {k.LAB_ACTOR_LABEL: 'vcpool-connector'})
        seen = k.observe(self.c, self.objects, self.client)
        self.assertEqual(sorted(r['workload'] for r in seen['labActors'].values()),
                         ['Deployment/connector-score', 'Deployment/nightscout-upstream'])
        self.assertFalse(any(name.startswith(('nightscout-upstream', 'connector-score')) for name in seen['pods']))

    def test_an_unlabelled_extra_deployment_is_still_refused(self):
        self.c['connectors'] = {'share': 0.25}
        add_deployment(self.client, self.c, 'nightscout-upstream', {})
        with self.assertRaisesRegex(Exception, 'POD_CONTROLLER'):
            k.observe(self.c, self.objects, self.client)

    def test_a_labelled_deployment_with_another_name_is_refused(self):
        self.c['connectors'] = {'share': 0.25}
        add_deployment(self.client, self.c, 'extra', {k.LAB_ACTOR_LABEL: 'vcpool-connector'})
        with self.assertRaisesRegex(Exception, 'POD_CONTROLLER'):
            k.observe(self.c, self.objects, self.client)

    def test_connector_lab_actors_are_refused_in_a_run_without_connectors(self):
        add_deployment(self.client, self.c, 'connector-score', {k.LAB_ACTOR_LABEL: 'vcpool-connector'})
        with self.assertRaisesRegex(Exception, 'POD_CONTROLLER'):
            k.observe(self.c, self.objects, self.client)


if __name__ == '__main__':
    unittest.main()
