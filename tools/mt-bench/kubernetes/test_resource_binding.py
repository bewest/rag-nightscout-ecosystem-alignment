"""Render the actual selected binding in scratch; no image or cluster effects.

Set K8S_BINDING_SOURCE to the deployment repository that owns the binding.
Missing source/tools explicitly skip this optional external-fixture qualification.
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


class ResourceBinding(unittest.TestCase):
    def setUp(self):
        source = os.environ.get('K8S_BINDING_SOURCE')
        if not source or not shutil.which('tk') or not shutil.which('node'):
            self.skipTest('K8S_BINDING_SOURCE, tk and node required')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        raw = subprocess.check_output(['git', '-C', source, 'archive', 'HEAD', 'bindings/kubernetes'])
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(self.root, filter='data')
        patch = Path(__file__).with_name('binding-input.patch')
        subprocess.run(['git', 'apply', '--directory=bindings/kubernetes', str(patch)], cwd=self.root, check=True)
        self.binding = self.root/'bindings/kubernetes'
        self.inputs = self.binding/'environments/synthetic/inputs.json'
        self.original = json.loads(self.inputs.read_text())
        self.inputs.with_name('main.jsonnet').write_text(
            "local ns=import 'ns/nightscout.libsonnet';local b=ns.new(import 'inputs.json');{render:b,inventory:b.inventory}")

    def render(self, mode, resources=None):
        self.inputs.write_text(json.dumps({**self.original, 'resourceAccounting': mode,
                                          **({'resources': resources} if resources else {})}))
        return json.loads(subprocess.check_output(['tk', 'eval', 'environments/synthetic'], cwd=self.binding))

    def containers(self, value):
        if isinstance(value, dict) and value.get('kind') in ('Deployment', 'StatefulSet', 'Job'):
            spec = value['spec']['template']['spec']
            yield from spec.get('containers', []) + spec.get('initContainers', [])
        elif isinstance(value, dict):
            for child in value.values():yield from self.containers(child)
        elif isinstance(value, list):
            for child in value:yield from self.containers(child)

    def budget(self, value):
        target = self.root/'render.json';target.write_text(json.dumps(value))
        script = "const c=require(process.argv[1]),x=require(process.argv[2]);console.log(JSON.stringify(c.checks(c.manifests(x.render),x.inventory).find(v=>v.name==='container-budgets')));"
        return json.loads(subprocess.check_output(['node', '-e', script,
            self.binding/'check/invariants.js', target]))['failures']

    def test_default_caps_and_explicit_no_caps_reach_actual_render_and_check(self):
        capped = self.render('limits-v1')
        self.assertTrue(list(self.containers(capped['render'])))
        self.assertTrue(all('limits' in c['resources'] for c in self.containers(capped['render'])))
        self.assertEqual(self.budget(capped), [])
        uncapped = self.render('requests-v1')
        self.assertTrue(all('limits' not in c['resources'] for c in self.containers(uncapped['render'])))
        self.assertEqual(self.budget(uncapped), [])
        uncapped['inventory']['resourceAccounting'] = 'limits-v1'
        self.assertTrue(self.budget(uncapped))
        uncapped['inventory']['resourceAccounting'] = 'requests-v1'
        self.assertEqual(self.budget(uncapped), [])

    def test_authored_partial_limits_do_not_inherit_reference_caps(self):
        current = self.render('requests-v1', {'api': {'limits': {'memory': '0.5Gi'}}})
        actors = list(self.containers(current['render']))
        self.assertEqual(next(c for c in actors if c['name']=='api')['resources']['limits'], {'memory':'0.5Gi'})
        self.assertTrue(all('limits' not in c['resources'] for c in actors if c['name']!='api'))
        self.assertEqual(self.budget(current), [])
        current = self.render('requests-v1', {'api': {'limits': None}})
        self.assertTrue(all('limits' not in c['resources'] for c in self.containers(current['render'])))
        self.assertEqual(self.budget(current), [])


if __name__ == '__main__':unittest.main()
