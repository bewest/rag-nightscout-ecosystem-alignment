"""Apply the commissioner patch to a new source copy and run offline controls.

Set K8S_COMMISSIONING_SOURCE to the directory containing the retained preflight.py,
controls.py, test-local.py, cleanup-plan.py and frozen.py. Source is read only.
No Kubernetes, cloud, Docker or application services are used. An absent source
is an explicit skip, not a passing commissioner qualification.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BASE_SHA256 = '8d49056b33569957efd9e62e335ca14839481de30eab6e2de1242671ca33eaa2'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CommissioningAccounting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supplied = os.environ.get('K8S_COMMISSIONING_SOURCE')
        if not supplied:
            raise unittest.SkipTest('K8S_COMMISSIONING_SOURCE absent; commissioner patch UNMEASURED')
        cls.source = Path(supplied).resolve()
        cls.assert_source = hashlib.sha256((cls.source/'preflight.py').read_bytes()).hexdigest()
        if cls.assert_source != BASE_SHA256:
            raise AssertionError('Commissioner base mismatch: '+cls.assert_source)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root/'bin'
        self.bin.mkdir()
        for name in ('preflight.py', 'controls.py', 'test-local.py', 'cleanup-plan.py', 'frozen.py'):
            shutil.copyfile(self.source/name, self.bin/name)
        command = ['git', 'apply', str(HERE/'commissioning-accounting.patch')]
        subprocess.run([*command[:2], '--check', *command[2:]], cwd=self.root, check=True, capture_output=True)
        subprocess.run(command, cwd=self.root, check=True, capture_output=True)
        self.p = load('commissioner_under_test', self.bin/'preflight.py')
        frozen = load('commissioner_frozen', self.bin/'frozen.py')
        cache = patch.dict(sys.modules, {'frozen': frozen})
        cache.start()
        self.addCleanup(cache.stop)
        self.env = json.loads((self.source.parent/'environment.example.json').read_text())
        self.env.update(targetNode='synthetic-node', placementByWorkload={})
        self.tree = self.fixture()
        self.snapshot = self.root/'snapshot'
        self.snapshot.mkdir()
        self.snapshot_fixture()

    def fixture(self):
        env = self.env
        def metadata(name, namespace=True):
            return {'name': name, **({'namespace': env['namespace']} if namespace else {}),
                    'labels': {'nightscout.org/run-id': env['runId']},
                    'annotations': {'nightscout.org/cleanup-owner': env['cleanupOwner']}}
        quota = {'pods': '30', 'persistentvolumeclaims': '0', 'services.loadbalancers': '0', 'services.nodeports': '0',
                 'requests.cpu': '100', 'requests.memory': '100Gi', 'requests.ephemeral-storage': '100Gi',
                 'limits.cpu': '100', 'limits.memory': '100Gi', 'limits.ephemeral-storage': '100Gi'}
        docs = [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': metadata(env['namespace'], False)},
                {'apiVersion': 'v1', 'kind': 'ResourceQuota', 'metadata': metadata('synthetic-budget'), 'spec': {'hard': quota}},
                {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRoleBinding',
                 'metadata': metadata(env['namespace']+'-vault-tokenreview', False),
                 'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': 'system:auth-delegator'},
                 'subjects': [{'kind': 'ServiceAccount', 'name': 'vault', 'namespace': env['namespace']}]},
                {'apiVersion': 'v1', 'kind': 'Service', 'metadata': metadata('synthetic-edge'),
                 'spec': {'type': 'ClusterIP', 'ports': [{'port': 8080}]}}]
        names = ('postgres', 'vault', 'cohort', 'pgstream', 'admin', 'ui', 'edge', 'provision', 'primer')
        for name in names:
            role = {'cohort': 'api', 'edge': 'nginx', 'provision': 'done'}.get(name, name)
            image = env['images'][role if role in ('postgres', 'vault', 'nginx') else 'app']
            resource = {'requests': {'cpu': '100m', 'memory': '64Mi', 'ephemeral-storage': '16Mi'},
                        'limits': {'cpu': '500m', 'memory': '256Mi', 'ephemeral-storage': '128Mi'}}
            spec = {'nodeName': env['targetNode'], 'imagePullSecrets': [{'name': env['imagePullSecret']}],
                    'containers': [{'name': role, 'image': image, 'resources': resource}],
                    'volumes': [{'name': 'tmp', 'emptyDir': {'sizeLimit': '16Mi'}}]}
            if name == 'cohort':
                spec['volumes'] += [{'name': 'secret-'+r, 'secret': {'secretName': 'ns-config-'+r}}
                                    for r in ('api', 'realtime', 'evaluator', 'tenant-admin')]
            docs.append({'apiVersion': 'batch/v1' if name in ('provision', 'primer') else 'apps/v1',
                         'kind': 'Job' if name in ('provision', 'primer') else 'StatefulSet' if name in ('postgres', 'vault', 'cohort') else 'Deployment',
                         'metadata': metadata(name), 'spec': {'replicas': 1,
                         'template': {'metadata': metadata(name), 'spec': spec}}})
        return docs

    def snapshot_fixture(self):
        node = {'metadata': {'name': self.env['targetNode']}, 'spec': {}, 'status': {
            'allocatable': {'cpu': '16', 'memory': '32Gi', 'ephemeral-storage': '200Gi', 'pods': '110'},
            'conditions': [{'type': name, 'status': 'True' if name == 'Ready' else 'False'}
                           for name in ('Ready', 'MemoryPressure', 'DiskPressure', 'PIDPressure', 'NetworkUnavailable')]}}
        self.write(self.snapshot/'nodes.json', {'items': [node]})
        self.write(self.snapshot/'pods.json', {'items': []})
        self.write(self.snapshot/'disk.json', [{'node': self.env['targetNode'], 'exit': 0,
                   'filesystemMetrics': ['node_filesystem_readonly{} 0', 'node_filesystem_avail_bytes{} 171798691840']}])
        (self.snapshot/'usage.txt').write_text(self.env['targetNode']+' 100m 1% 1024Mi 3%\n')

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def object(self, kind, name=None):
        return next(o for o in self.tree if o['kind'] == kind and (name is None or o['metadata']['name'] == name))

    def containers(self):
        return [c for o in self.tree if o['kind'] in ('Deployment', 'StatefulSet', 'Job')
                for c in self.p.podspec(o)['containers'] + self.p.podspec(o).get('initContainers', [])]

    def requests_mode(self):
        self.env['resourceAccounting'] = 'requests-v1'
        hard = self.object('ResourceQuota')['spec']['hard']
        for key in list(hard):
            if key.startswith('limits.'):
                del hard[key]

    def test_patch_applies_to_verified_base_and_legacy_controls_remain_red(self):
        trial = self.p.static(self.env, self.tree)
        self.assertEqual(trial['resourceAccounting'], 'limits-v1')
        self.assertEqual(trial['accounted'], trial['limits'])
        self.write(self.root/'environment.example.json', self.env)
        self.write(self.root/'render.json', self.tree)
        legacy = subprocess.run([sys.executable, '-B', self.bin/'test-local.py'], cwd=self.bin,
                                capture_output=True, text=True)
        self.assertEqual(legacy.returncode, 0, legacy.stdout+legacy.stderr)
        controls = subprocess.run([sys.executable, '-B', self.bin/'controls.py', '--environment',
                                   self.root/'environment.example.json', '--rendered', self.root/'render.json',
                                   '--snapshot', self.snapshot], cwd=self.bin, capture_output=True, text=True)
        self.assertEqual(controls.returncode, 0, controls.stdout+controls.stderr)
        rows = json.loads(controls.stdout)['controls']
        self.assertEqual(len(rows), 18)
        self.assertTrue(all(row['broken'] == 'REFUSED' and row['restored'] == 'PASS' for row in rows))

    def test_requests_fit_while_limit_overcommit_still_fails_legacy(self):
        for c in self.containers():
            c['resources']['limits']['cpu'] = '4'
        legacy = self.p.static(self.env, self.tree)
        with self.assertRaisesRegex(self.p.Refused, 'cpu headroom'):
            self.p.headroom(self.snapshot, legacy, self.env['targetNode'])
        self.requests_mode()
        trial = self.p.static(self.env, self.tree)
        self.assertAlmostEqual(trial['accounted']['cpu'], .9)
        self.assertEqual(trial['limits']['cpu'], 36)
        self.assertTrue(self.p.headroom(self.snapshot, trial, self.env['targetNode'])[0]['trialFits'])
        self.assertIn('do not establish a hard usage bound', trial['accountingScope'])

    def test_absent_and_partial_limits_are_unbounded_not_zero(self):
        self.requests_mode()
        first = self.containers()[0]
        first['resources'].pop('limits')
        trial = self.p.static(self.env, self.tree)
        self.assertEqual(trial['limits'], dict.fromkeys(self.p.DIMS))
        self.assertEqual(json.loads(json.dumps(trial))['limits'], dict.fromkeys(self.p.DIMS))
        self.p.placed_headroom(self.snapshot, trial)
        first['resources']['limits'] = {'memory': '128Mi'}
        trial = self.p.static(self.env, self.tree)
        self.assertIsNone(trial['limits']['cpu'])
        self.assertIsNone(trial['limits']['ephemeral-storage'])
        self.assertEqual(trial['limits']['memory'], (8*256+128)*1024**2)
        self.env['resourceAccounting'] = 'limits-v1'
        with self.assertRaisesRegex(self.p.Refused, 'omitted limits'):
            self.p.static(self.env, self.tree)

    def test_invalid_request_or_supplied_limit_refuses_and_restores(self):
        self.requests_mode()
        baseline = self.p.static(self.env, self.tree)
        for group, value in (('requests', None), ('requests', '0'), ('requests', '-1'),
                             ('limits', '0'), ('limits', '50m'), ('limits', 'invalid')):
            with self.subTest(group=group, value=value):
                c = self.containers()[0]
                before = copy.deepcopy(c['resources'])
                if value is None:
                    del c['resources'][group]['cpu']
                else:
                    c['resources'][group]['cpu'] = value
                with self.assertRaises((self.p.Refused, ValueError)):
                    self.p.static(self.env, self.tree)
                c['resources'] = before
                self.assertEqual(self.p.static(self.env, self.tree), baseline)

    def test_exact_quantity_domain_matches_shared_parser_without_json_decimals(self):
        import resource_budget as shared
        from test_adapter import k
        self.requests_mode()
        for value in ('1e3', '1Pi', '+0.5Gi', '0.1', '250m'):
            with self.subTest(value=value):
                self.assertEqual(self.p.scheduling_quantity(value, 'memory'), shared.quantity(value, False, k.need))
                self.assertEqual(self.p.scheduling_quantity(value, 'cpu')*1000, shared.quantity(value, True, k.need))
                for c in self.containers():
                    c['resources']['requests']['memory'] = value
                    c['resources'].pop('limits', None)
                self.object('ResourceQuota')['spec']['hard']['requests.memory'] = '100Pi'
                trial = self.p.static(self.env, self.tree)
                self.assertIsInstance(json.loads(json.dumps(trial))['requests']['memory'], (int, float))
        for value in ('NaN', 'Infinity', '-1', '1e999999', True):
            with self.subTest(invalid=value), self.assertRaises(self.p.Refused):
                self.p.quantity(value)

    def test_limit_request_order_checked_before_rounding_to_scheduling_units(self):
        self.requests_mode()
        first = self.containers()[0]
        first['resources']['requests']['memory'] = '0.9'
        first['resources']['limits']['memory'] = '0.1'
        self.assertEqual(self.p.scheduling_quantity('0.9', 'memory'), 1)
        self.assertEqual(self.p.scheduling_quantity('0.1', 'memory'), 1)
        with self.assertRaisesRegex(self.p.Refused, 'omitted limits or requests'):
            self.p.static(self.env, self.tree)
        first['resources']['limits']['memory'] = '0.9'
        trial = self.p.static(self.env, self.tree)
        self.assertEqual(trial['requests']['memory'], 1+8*64*1024**2)

    def test_owned_unknown_dimensions_fail_early_but_peer_dimensions_are_observed(self):
        self.requests_mode()
        baseline = self.p.static(self.env, self.tree)
        first = self.containers()[0]
        for group in ('requests', 'limits'):
            first['resources'][group]['example.test/synthetic-device'] = '1'
            with self.assertRaisesRegex(self.p.Refused, 'unsupported resource dimension'):
                self.p.static(self.env, self.tree)
            del first['resources'][group]['example.test/synthetic-device']
            self.assertEqual(self.p.static(self.env, self.tree), baseline)
        peer = {'spec': {'nodeName': self.env['targetNode'], 'containers': [{'resources': {
            'requests': {'cpu': '1m', 'memory': '1Mi', 'ephemeral-storage': '1Mi', 'example.test/synthetic-device': '1'},
            'limits': {'cpu': '10m', 'memory': '2Mi', 'ephemeral-storage': '2Mi', 'example.test/synthetic-device': '1'}}}]},
            'status': {'phase': 'Running'}}
        self.write(self.snapshot/'pods.json', {'items': [peer]})
        observed = self.p.headroom(self.snapshot, baseline, self.env['targetNode'])[0]
        self.assertTrue(observed['trialFits'])
        self.assertEqual(observed['peerRequests']['memory'], 1024**2)

    def test_quotas_and_limitrange_must_not_force_hidden_limits(self):
        self.requests_mode()
        hard = self.object('ResourceQuota')['spec']['hard']
        for dimension in self.p.DIMS:
            hard['limits.'+dimension] = '100Gi'
            with self.assertRaisesRegex(self.p.Refused, 'quota forces limits'):
                self.p.static(self.env, self.tree)
            del hard['limits.'+dimension]
            self.p.static(self.env, self.tree)
        metadata = copy.deepcopy(self.object('ResourceQuota')['metadata'])
        metadata['name'] = 'synthetic-defaults'
        item = {'apiVersion': 'v1', 'kind': 'LimitRange', 'metadata': metadata,
                'spec': {'limits': [{'type': 'Container', 'default': {'cpu': '1'}}]}}
        self.tree.append(item)
        with self.assertRaisesRegex(self.p.Refused, 'default limits'):
            self.p.static(self.env, self.tree)
        item['spec']['limits'] = [{'type': 'Container', 'min': {'cpu': '1m'}}]
        self.p.static(self.env, self.tree)
        key = 'requests.memory'
        del hard[key]
        with self.assertRaisesRegex(self.p.Refused, 'resource quota too small'):
            self.p.static(self.env, self.tree)

    def test_phase_peaks_include_sidecars_overhead_and_unknown_limit(self):
        def container(cpu, memory, disk, restart=False):
            resources = {'cpu': str(cpu)+'m', 'memory': str(memory)+'Mi', 'ephemeral-storage': str(disk)+'Mi'}
            return {'resources': {'requests': resources, 'limits': copy.deepcopy(resources)},
                    **({'restartPolicy': 'Always'} if restart else {})}
        spec = {'containers': [container(100, 700, 10)], 'initContainers': [container(500, 32, 900),
                container(200, 250, 100, True), container(700, 64, 400), container(150, 200, 80, True)],
                'overhead': {'cpu': '10m', 'memory': '12Mi', 'ephemeral-storage': '30Mi'}}
        expected = {'cpu': .91, 'memory': 1162*1024**2, 'ephemeral-storage': 930*1024**2}
        for which in ('requests', 'limits'):
            for key, value in self.p.effective(spec, which).items():
                self.assertAlmostEqual(value, expected[key])
        del spec['initContainers'][0]['resources']['limits']['memory']
        self.assertIsNone(self.p.effective(spec, 'limits')['memory'])
        self.assertEqual(self.p.effective(spec)['memory'], expected['memory'])
        spec['resources'] = {'requests': {'cpu': '8'}}
        with self.assertRaisesRegex(self.p.Refused, 'Pod-level'):
            self.p.effective(spec)

    def test_mode_and_accounted_budget_mismatch_refuse(self):
        self.env['resourceAccounting'] = 'typo'
        with self.assertRaisesRegex(self.p.Refused, 'accounting mode'):
            self.p.static(self.env, self.tree)
        self.requests_mode()
        trial = self.p.static(self.env, self.tree)
        broken = copy.deepcopy(trial)
        broken['accounted'] = broken['limits']
        with self.assertRaisesRegex(self.p.Refused, 'accounting budget mismatch'):
            self.p.headroom(self.snapshot, broken)
        del broken['accounted']
        with self.assertRaisesRegex(self.p.Refused, 'accounting budget mismatch'):
            self.p.headroom(self.snapshot, broken)
        self.p.headroom(self.snapshot, trial, self.env['targetNode'])

    def test_request_overcommit_and_missing_observation_remain_red(self):
        self.requests_mode()
        trial = self.p.static(self.env, self.tree)
        self.p.placed_headroom(self.snapshot, trial)
        for c in self.containers():
            c['resources']['requests']['cpu'] = '4'
            c['resources']['limits']['cpu'] = '4'
        trial = self.p.static(self.env, self.tree)
        with self.assertRaisesRegex(self.p.Refused, 'cpu headroom'):
            self.p.placed_headroom(self.snapshot, trial)
        self.tree = self.fixture()
        self.requests_mode()
        trial = self.p.static(self.env, self.tree)
        (self.snapshot/'usage.txt').unlink()
        with self.assertRaisesRegex(self.p.Refused, 'usage UNMEASURED'):
            self.p.placed_headroom(self.snapshot, trial)


if __name__ == '__main__':
    unittest.main(verbosity=2)
