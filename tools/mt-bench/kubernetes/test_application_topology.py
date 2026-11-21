"""Profile controls use the actual adapter census and UID cleanup planner."""
import ast
import copy
from contextlib import contextmanager
from pathlib import Path
import unittest

import application_topology as topology
import kube_adapter as k
import frozen
import toolchain
from test_adapter import fixture
import test_toolchain


def separate_fixture():
    c, inventory, old, _ = fixture()
    c[topology.FIELD] = inventory[topology.FIELD] = topology.SEPARATE
    base = old[1]
    prototype = base['spec']['template']['spec']['containers'][0]
    rendered = [old[0]]
    c['roles'] = {**topology.role_mapping(topology.SEPARATE),
                  'postgres': {'workload': 'StatefulSet/postgres', 'container': 'postgres'}}
    for name, kind in topology.SEPARATE_WORKLOADS.items():
        obj = copy.deepcopy(base)
        obj['kind'] = kind
        obj['metadata']['name'] = name
        obj['apiVersion'] = 'batch/v1' if kind == 'Job' else 'apps/v1'
        obj['spec']['strategy'] = {'type': 'Recreate'}
        container = copy.deepcopy(prototype)
        container.update(name=name, command=['synthetic', name])
        obj['spec']['template']['spec']['containers'] = [container]
        rendered.append(obj)
    class Replies:
        def __init__(self):
            self.objects = {}
            self.pods = []
            self.replicas = []
            for original in rendered:
                obj = copy.deepcopy(original)
                obj['metadata'].update(uid='uid-'+obj['metadata']['name'], resourceVersion='10')
                self.objects[k.key(obj)] = obj
                if obj['kind'] == 'Namespace':
                    continue
                name = obj['metadata']['name']
                parent = {'kind': obj['kind'], 'name': name, 'uid': obj['metadata']['uid'], 'controller': True}
                if obj['kind'] == 'Deployment':
                    replica = {'apiVersion': 'apps/v1', 'kind': 'ReplicaSet',
                               'metadata': {**copy.deepcopy(obj['metadata']), 'name': name+'-rs', 'uid': name+'-rs',
                                            'ownerReferences': [parent]}}
                    self.replicas.append(replica)
                    parent = {'kind': 'ReplicaSet', 'name': name+'-rs', 'uid': name+'-rs', 'controller': True}
                pod = {'kind': 'Pod', 'apiVersion': 'v1', 'metadata': {**copy.deepcopy(obj['metadata']),
                       'name': name+'-pod', 'uid': name+'-pod', 'ownerReferences': [parent]},
                       'spec': {**copy.deepcopy(obj['spec']['template']['spec']), 'nodeName': 'synthetic-worker'},
                       'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}],
                                  'containerStatuses': [{'name': name, 'containerID': 'containerd://'+name,
                                  'imageID': c['pins']['appImageId'], 'restartCount': 0, 'ready': True,
                                  'state': {'running': {}}}]}}
                self.pods.append(pod)
        def get(self, kind, name=None, cleanup=False):
            if kind == 'namespace':
                return copy.deepcopy(self.objects['Namespace/'+name])
            if kind == 'replicasets':
                return {'items': copy.deepcopy(self.replicas)}
            if kind == 'pods':
                return {'items': copy.deepcopy(self.pods)}
            return copy.deepcopy(self.objects[kind+'/'+name])
    return c, inventory, rendered, Replies()


class ApplicationTopology(unittest.TestCase):
    def setUp(self):
        self.c, self.inventory, self.rendered, self.client = separate_fixture()

    def validate(self):
        return k.validate(self.c, self.inventory, self.rendered)

    def test_inventory_roles_and_cleanup_cover_all_eleven_workloads(self):
        objects = self.validate()
        baseline = k.observe(self.c, objects, self.client)
        self.assertEqual(len(baseline['pods']), 11)
        for role in topology.ROLES:
            self.assertEqual(k.selected_pod(self.c, baseline, role), (role+'-pod', role))
        plan = k.cleanup_plan(self.c, baseline, k.observe(self.c, objects, self.client, baseline))
        self.assertEqual(len(plan['actions']), 11)
        self.assertEqual({row['object']['kind']+'/'+row['object']['name'] for row in plan['actions']},
                         {kind+'/'+name for name, kind in topology.SEPARATE_WORKLOADS.items()})
        self.assertTrue(all(row['stdin']['preconditions']['uid'] for row in plan['actions']))
        changed = copy.deepcopy(baseline)
        changed['objects']['Deployment/evaluator']['uid'] = 'peer'
        with self.assertRaisesRegex(k.Refused, 'PEER_CLEANUP_REFUSED'):
            k.cleanup_plan(self.c, baseline, changed)
        k.cleanup_plan(self.c, baseline, baseline)

    def test_wrong_profile_mapping_overlap_process_and_socket_controls(self):
        baseline = self.validate()
        cases = []
        cases.append((self.inventory, topology.FIELD, topology.COHORT, 'APPLICATION_TOPOLOGY_CHANGED'))
        cases.append((self.c['roles'], 'evaluator', {'workload': 'StatefulSet/cohort', 'container': 'evaluator'}, 'APPLICATION_ROLE_TOPOLOGY'))
        api = next(obj for obj in self.rendered if obj['metadata']['name'] == 'api')
        cases.append((api['spec'], 'replicas', 2, 'APPLICATION_WORKLOAD_REPLACEMENT'))
        cases.append((api['spec'], 'strategy', {'type': 'RollingUpdate'}, 'APPLICATION_WORKLOAD_REPLACEMENT'))
        pod = api['spec']['template']['spec']
        cases.append((pod, 'containers', pod['containers']+[dict(pod['containers'][0], name='peer-role')], 'APPLICATION_PROCESS_ROSTER'))
        cases.append((pod, 'volumes', [{'name': 'ns-ipc', 'emptyDir': {}}], 'APPLICATION_SOCKET_VOLUME'))
        for target, key, value, symptom in cases:
            existed = key in target
            previous = target.get(key)
            target[key] = value
            with self.assertRaisesRegex(k.Refused, symptom):
                self.validate()
            if existed:
                target[key] = previous
            else:
                del target[key]
            self.assertEqual(self.validate(), baseline)
            print('RED_RESTORED', symptom)
        omitted = self.rendered.pop()
        with self.assertRaisesRegex(k.Refused, 'APPLICATION_WORKLOAD_ROSTER'):
            self.validate()
        self.rendered.append(omitted)
        self.validate()
        duplicate = copy.deepcopy(api)
        duplicate['kind'] = 'StatefulSet'
        self.rendered.append(duplicate)
        with self.assertRaisesRegex(k.Refused, 'APPLICATION_WORKLOAD_ROSTER'):
            self.validate()
        self.rendered.pop()
        self.validate()

    def test_actual_pod_and_process_identity_remain_strict(self):
        objects = self.validate()
        baseline = k.observe(self.c, objects, self.client)
        api = next(pod for pod in self.client.pods if pod['metadata']['name'] == 'api-pod')
        duplicate = copy.deepcopy(api)
        duplicate['metadata'].update(name='api-overlap', uid='overlap')
        self.client.pods.append(duplicate)
        with self.assertRaisesRegex(k.Refused, 'ROLE_POD_UNMEASURED:api'):
            k.observe(self.c, objects, self.client, baseline)
        self.client.pods.pop()
        state = api['status']['containerStatuses'][0]
        state.update(containerID='containerd://new-api', restartCount=1)
        changed = k.observe(self.c, objects, self.client, baseline, restarted_role='api')
        self.assertEqual(changed['pods']['evaluator-pod'], baseline['pods']['evaluator-pod'])
        state.update(containerID='containerd://api', restartCount=0)
        k.observe(self.c, objects, self.client, baseline)

    def test_legacy_profile_is_unchanged_and_selection_is_bound(self):
        c, inventory, rendered, _ = fixture()
        k.validate(c, inventory, rendered)
        self.assertEqual(topology.bind({}, c, inventory, k.need), {})
        self.assertEqual(topology.bind({topology.FIELD: topology.SEPARATE}, {}, self.inventory, k.need),
                         {topology.FIELD: topology.SEPARATE})
        with self.assertRaisesRegex(k.Refused, 'APPLICATION_TOPOLOGY_CHANGED'):
            topology.bind({}, {}, self.inventory, k.need)
        with self.assertRaisesRegex(k.Refused, 'APPLICATION_TOPOLOGY_UNSUPPORTED'):
            topology.selection({topology.FIELD: 'separate-k2'}, k.need)

    def test_common_intent_projects_explicit_profile_into_renderer_inputs(self):
        manifest = test_toolchain.Toolchain().manifest()
        manifest['kubernetes'] = {topology.FIELD: topology.SEPARATE}
        # The legacy intent reached Kubernetes only through the external pgstream service.
        self.assertNotIn(topology.FIELD, toolchain.legacy(manifest, 'compose'))
        with self.assertRaisesRegex(ValueError, 'KUBERNETES_TOPOLOGY_UNSUPPORTED'):
            toolchain.legacy(manifest)

    def test_each_separate_serving_role_gets_existing_serving_window(self):
        source = Path(__file__).with_name('lifecycle.py')
        nodes = [node for node in ast.parse(source.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in ('workload_ready',)]
        called = []
        @contextmanager
        def window(*_):
            yield
        scope = {'application_topology': topology, 'intent': {topology.FIELD: topology.SEPARATE},
                 'frozen': frozen, 'producer_policy': None, 'startup_window': window,
                 'ready': lambda *args: called.append(args), 'objects': lambda _: [
                     dict(obj, spec={**obj['spec'], 'selector': {'matchLabels': {'role': obj['metadata']['name']}}})
                     for obj in self.rendered if obj['kind'] != 'Namespace'],
                 'waits': {'cohortReadySeconds': 900, 'workloadReadySeconds': 300}}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
        scope['workload_ready']('serving')
        observed = {row[1]: row[2] for row in called}
        self.assertEqual({role: observed[role] for role in topology.ROLES}, {role: 900 for role in topology.ROLES})
        self.assertTrue(all(topology.readiness_signal(scope['intent'], role, k.need) for role in topology.ROLES))


if __name__ == '__main__':
    unittest.main()
