"""Exact private-source patch and real offline compiler/preparation controls.

Supply K8S_POPULATION_COMMISSIONER (directory containing ops/),
K8S_POPULATION_PREPARER, K8S_POPULATION_PACKET, and K8S_POPULATION_JSONNET.
Absent private inputs skip explicitly; no Docker/Kubernetes/cloud calls occur.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import commissioning_population as c

HERE = Path(__file__).resolve().parent


class PrivatePopulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ('COMMISSIONER', 'PREPARER', 'PACKET', 'JSONNET')
        if not all(os.environ.get('K8S_POPULATION_'+name) for name in names):
            raise unittest.SkipTest('exact private population constructor inputs absent')
        cls.source, cls.preparer, cls.packet, cls.compiler = (
            Path(os.environ['K8S_POPULATION_'+name]).resolve() for name in names)

    def setUp(self):
        self.temp = TemporaryDirectory(dir=os.environ.get('K8S_POPULATION_SCRATCH'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root/'private'
        self.receipt = c.materialize(self.source, self.preparer, self.private)
        self.stage = self.private/'ops/staging-k8s'
        self.environment = json.loads((self.packet/'actor-free-environment.json').read_text())
        self.intent = json.loads((self.packet/'intent.json').read_text())
        self.package = self.packet/'binding/bindings/kubernetes'
        self.ceiling = self.intent['profile']['population']['maxTenants']
        self.assertEqual(self.environment['populationCeiling'], self.ceiling)

    def render(self, environment, *, overlay=None, package=None, inventory=False):
        path = self.root/'render-input.json'
        path.write_text(json.dumps(environment))
        expression = "local b=import 'lib/ns/nightscout.libsonnet'; local o=import "+json.dumps(
            str(overlay or self.stage/'overlay.libsonnet'))+"; o(b,std.extVar('PRIVATE_ENV'))"
        if inventory:
            expression = '('+expression+').inventory'
        return subprocess.run([self.compiler, '-J', package or self.package,
            '--ext-code-file', 'PRIVATE_ENV='+str(path), '-e', expression],
            capture_output=True, timeout=35)

    def test_exact_render_omission_compatibility_and_dropped_projection_red_restored(self):
        good = self.render(self.environment)
        self.assertEqual(good.returncode, 0, good.stderr.decode())
        inventory = self.render(self.environment, inventory=True)
        self.assertEqual(inventory.returncode, 0, inventory.stderr.decode())
        self.assertEqual(json.loads(inventory.stdout)['populationCeiling'], self.ceiling)
        original = self.source/'ops/staging-k8s/overlay.libsonnet'
        broken = self.render(self.environment, overlay=original)
        self.assertNotEqual(broken.returncode, 0)
        self.assertIn(b'population ceiling changed from bound source contract', broken.stderr)
        for value in (None, self.ceiling+1):
            wrong = copy.deepcopy(self.environment)
            if value is None:
                wrong.pop('populationCeiling')
            else:
                wrong['populationCeiling'] = value
            result = self.render(wrong)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'population ceiling changed from bound source contract', result.stderr)
        self.assertEqual(self.render(self.environment).stdout, good.stdout)
        # Unselected source context is a synthetic omission control, never a
        # replacement for the actual selected source contract or actor input.
        package = self.root/'unselected-source-context'
        shutil.copytree(self.package, package)
        contract = package/'assets/source-contract.json'
        value = json.loads(contract.read_text())
        value.pop('populationCeiling')
        value.pop('populationSource', None)
        contract.write_text(json.dumps(value))
        omitted = copy.deepcopy(self.environment)
        omitted.pop('populationCeiling')
        for view in (False, True):
            old = self.render(omitted, overlay=original, package=package, inventory=view)
            new = self.render(omitted, package=package, inventory=view)
            self.assertEqual(old.returncode, 0, old.stderr.decode())
            self.assertEqual(new.returncode, 0, new.stderr.decode())
            self.assertEqual(old.stdout, new.stdout)
        print('RED_RESTORED actual private projection; omitted output byte-identical')

    def prepare(self, name, *, private=None):
        private = private or self.private
        base = self.root/'base-case'
        base.mkdir(exist_ok=True)
        (base/'environment.json').write_text(json.dumps(self.environment))
        # Inert template: this source/preparation test never runs its driver.
        (base/'native-run-template.json').write_text(json.dumps({'driver': {}}))
        delivery = self.root/'planned-delivery.json'
        selected = json.loads((self.packet/'preparation.json').read_text())
        delivery.write_text(json.dumps({'targetReference': self.environment['images']['app'],
                                        'appImageId': selected['configDigest']}))
        requests = self.root/'requests.json'
        requests.write_text(json.dumps({'resources': self.environment['resources']}))
        command = [sys.executable, '-B', private/'prepare-private-case.py',
            '--out', self.root/name, '--intent', self.packet/'intent.json',
            '--binding', self.packet/'binding', '--instrument', HERE.parents[2],
            '--base-case', base, '--delivery', delivery, '--planned-delivery',
            '--commissioner', private/'ops/staging-k8s', '--jsonnet', self.compiler,
            '--work', str(self.environment['workDeadlineSeconds']),
            '--provision', str(self.environment['provisionDeadlineSeconds']),
            '--cleanup', str(self.environment['cleanupDeadlineSeconds']),
            '--requests-v1', '--requests-file', requests]
        if 'receiverStageObservation' in self.environment:
            command.append('--receiver-trace')
        if 'evaluatorFailureTraceLimit' in self.environment:
            command += ['--evaluator-failure-limit', str(self.environment['evaluatorFailureTraceLimit'])]
        if 'resourcePhasePlan' in self.environment:
            command += ['--resource-phase-plan', self.environment['resourcePhasePlan']['contract']]
        return subprocess.run(command, capture_output=True, timeout=90)

    def test_real_preparation_and_private_controller_refuse_lost_changed_or_old_selection(self):
        result = self.prepare('selected-case')
        self.assertEqual(result.returncode, 0, (result.stdout+result.stderr).decode())
        case = self.root/'selected-case'
        environment = json.loads((case/'environment.json').read_text())
        self.assertEqual(environment['populationCeiling'], self.ceiling)
        self.assertTrue((case/'stages/provision.json').is_file())
        # This runs the copied controller's real static preflight in a new
        # process, including its exact source-contract and image/budget checks.
        code = "import sys,json;sys.path.insert(0,sys.argv[1]);import preflight;print(json.dumps(preflight.static(json.load(open(sys.argv[2])),json.load(open(sys.argv[3]))),sort_keys=True))"
        def static(value):
            path = self.root/'static-environment.json'
            path.write_text(json.dumps(value))
            return subprocess.run([sys.executable, '-B', '-c', code, self.stage/'bin',
                                   path, case/'render.json'], capture_output=True, timeout=30)
        baseline = static(environment)
        self.assertEqual(baseline.returncode, 0, baseline.stderr.decode())
        for value in (None, self.ceiling+1):
            wrong = copy.deepcopy(environment)
            if value is None:
                wrong.pop('populationCeiling')
            else:
                wrong['populationCeiling'] = value
            bad = static(wrong)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn(b'experiment population ceiling changed', bad.stderr)
        render_path = case/'render.json'
        original_render = render_path.read_bytes()
        try:
            for drop in (False, True):
                tree = json.loads(original_render)
                def objects(value):
                    if isinstance(value, list):
                        for item in value:
                            yield from objects(item)
                    elif isinstance(value, dict):
                        if 'apiVersion' in value and 'kind' in value:
                            yield value
                        else:
                            for item in value.values():
                                yield from objects(item)
                job, = [o for o in objects(tree) if o.get('kind') == 'Job'
                        and o['metadata']['name'] == 'provision']
                bootstrap, = [actor for actor in job['spec']['template']['spec']['initContainers']
                              if actor['name'] == 'bootstrap']
                field, = [row for row in bootstrap['env'] if row['name'] == 'NS_DEMO_POPULATION_CEILING']
                if drop:
                    bootstrap['env'].remove(field)
                else:
                    field['value'] = str(self.ceiling+1)
                render_path.write_text(json.dumps(tree))
                bad = static(environment)
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn(b'rendered population ceiling mismatch', bad.stderr)
        finally:
            render_path.write_bytes(original_render)
        frozen = self.stage/'bin/frozen.py'
        saved = frozen.read_bytes()
        try:
            frozen.write_bytes((self.source/'ops/staging-k8s/bin/frozen.py').read_bytes())
            old = static(environment)
            self.assertNotEqual(old.returncode, 0)
            self.assertIn(b'population ceiling unsupported by private source', old.stderr)
        finally:
            frozen.write_bytes(saved)
        self.assertEqual(static(environment).stdout, baseline.stdout)
        print('RED_RESTORED actual private preflight selection and old validator refusal')

    def test_preparation_projects_once_and_refuses_stale_omission(self):
        body = ast.parse((self.private/'prepare-private-case.py').read_text()).body
        start = next(i for i, node in enumerate(body) if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'environment' for t in node.targets))
        code = compile(ast.Module(body=body[start:start+2], type_ignores=[]), '<actual-preparation-selection>', 'exec')
        def project(selected, inherited):
            scope = {'selected': selected, 'read': lambda path: copy.deepcopy(inherited),
                     'args': type('Args', (), {'base_case': self.root})()}
            exec(code, scope)
            return scope['environment']
        self.assertEqual(project({'populationCeiling': self.ceiling}, {}), {'populationCeiling': self.ceiling})
        self.assertEqual(project({}, {'unchanged': True}), {'unchanged': True})
        with self.assertRaisesRegex(AssertionError, 'POPULATION_CEILING_UNDECLARED'):
            project({}, {'populationCeiling': self.ceiling})

    def test_source_and_patch_mismatch_refuse_before_new_output(self):
        with patch.object(c, 'PATCH_SHA256', '0'*64):
            with self.assertRaisesRegex(ValueError, 'PATCH_CHANGED'):
                c.materialize(self.source, self.preparer, self.root/'wrong-patch')
        wrong = self.root/'wrong-preparer.py'
        wrong.write_bytes(self.preparer.read_bytes()+b'\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'BASE_CHANGED'):
            c.materialize(self.source, wrong, self.root/'wrong-base')
        self.assertFalse((self.root/'wrong-patch').exists())
        self.assertFalse((self.root/'wrong-base').exists())

    def test_output_aliases_into_own_source_fixture_refuse_before_mkdir_or_copy(self):
        source = self.root/'input-source'
        shutil.copytree(self.source/'ops/staging-k8s', source/'ops/staging-k8s')
        (source/'ops/bin').mkdir(parents=True)
        shutil.copy2(self.source/'ops/bin/ro', source/'ops/bin/ro')
        outside = self.root/'outside'
        outside.mkdir()
        alias = self.root/'source-alias'
        alias.symlink_to(source, target_is_directory=True)
        outputs = (outside/'..'/'input-source'/'lexical-child', alias/'symlink-child')
        for output in outputs:
            resolved = output.resolve(strict=False)
            self.assertFalse(resolved.exists())
            with patch.object(c.shutil, 'copytree', side_effect=AssertionError('source copy attempted')) as copy_source:
                with self.assertRaisesRegex(ValueError, 'OUTPUT_SCOPE'):
                    c.materialize(source, self.preparer, output)
                copy_source.assert_not_called()
            self.assertFalse(resolved.exists())
        print('RED_RESTORED dotdot and symlink-parent outputs refuse before source write')


if __name__ == '__main__':
    unittest.main()
