"""Public offline preparation against an operator-selected binding and frozen package."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import kube_adapter as k


class StandardCase(unittest.TestCase):
    @unittest.skipUnless(all(os.environ.get('K8S_STANDARD_' + key) for key in
                             ('TEMPLATE', 'PACKAGE', 'BINDING', 'PROFILE')), 'needs a frozen discovery package')
    def test_public_cli_prepares_two_points_without_source_writes_or_historical_capacity(self):
        paths = {key:Path(os.environ['K8S_STANDARD_' + key]).resolve()
                 for key in ('TEMPLATE', 'PACKAGE', 'BINDING', 'PROFILE')}
        template = paths['TEMPLATE']
        inputs = [template/name for name in ('intent.json','environment.json','lifecycle-input.json',
                                             'binding-inputs.json','native-run-template.json')]
        inputs += list((template/'stages').glob('*.json'))
        inputs += [paths['PROFILE'], paths['PACKAGE']/'source-receipt.json', paths['PACKAGE']/'build-receipt.json',
                   paths['PACKAGE']/'runner-image-delivery.json', paths['BINDING']/'binding.json']
        inputs += [p for p in (paths['BINDING']/'bindings/kubernetes').rglob('*') if p.is_file()]
        def checksums():
            return {p:hashlib.sha256(p.read_bytes()).digest() for p in inputs}
        initial = checksums()
        cli = [sys.executable, '-B', k.HERE/'experiment.py']
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            profile = k.document(paths['PROFILE'])
            profile['proposedEnvelope'] = {'clusterLimits':{'invalid':0}, 'nativeLimits':{'millicpus':1,'memoryBytes':1}}
            profile['workload'].update(loadSeconds=600, drainSeconds=300)
            selected = root/'profile.json'
            for i, (tenants, scale) in enumerate(((1000, 1), (3000, 1/3))):
                output = root/('standard-test-'+str(i))
                profile['population'].update(provisionedTenants=tenants, ordinaryRosterTenants=tenants)
                profile['workload']['workloadScale'] = scale
                k.write(selected, profile)
                cmd = cli + ['standard', template, paths['PACKAGE'], selected, output, '--binding', paths['BINDING']]
                if i == 0:
                    refused = subprocess.run(cmd+['--reserved-worker-taint','bad'],capture_output=True,text=True)
                    self.assertEqual(json.loads(refused.stderr)['code'],'K8S_STANDARD_RESERVED_WORKER_TAINT')
                    self.assertFalse(output.exists())
                    failed, = root.glob(output.name+'.failed-*')
                    self.assertEqual(k.document(failed/'prepare-error.json')['liveActors'],0)
                taint = ['--reserved-worker-taint','worker=reserved'] if i == 0 else []
                result = json.loads(subprocess.check_output(cmd + taint))
                self.assertFalse(result['runtimeStarted'])
                final = k.document(output/'intent.json')
                fixed = k.document(output/'lifecycle-bound.json')
                self.assertNotIn('snapshotDirectory', fixed)
                self.assertEqual(final['profile']['population']['provisionedTenants'], tenants)
                self.assertEqual(final['profile']['workload']['workloadScale'], scale)
                self.assertNotIn('invalid', final['profile']['proposedEnvelope']['clusterLimits'])
                self.assertEqual(final['profile']['proposedEnvelope']['nativeLimits'],
                                 k.document(template/'lifecycle-input.json')['nativeLimits'])
                objs = k.manifests(k.document(output/'render.json'))
                self.assertTrue({'ResourceQuota', 'LimitRange'}.isdisjoint(obj['kind'] for obj in objs))
                for obj in objs:
                    if obj['kind'] in k.WORKLOADS:
                        pod = k.template(obj)['spec']
                        self.assertFalse(any(pod.get(key) for key in ('nodeName','nodeSelector','affinity')))
                        self.assertEqual(pod.get('tolerations',[]), [{'key':'worker','value':'reserved',
                                         'operator':'Equal','effect':'NoSchedule'}] if taint else [])
                job, = [o for o in objs if o['kind']=='Job' and o['metadata']['name']=='k6']
                declared = k.document(paths['BINDING']/'bindings/kubernetes/lib/ns/typical-requests.json')
                for actor in job['spec']['template']['spec']['containers']+job['spec']['template']['spec']['initContainers']:
                    self.assertEqual(actor['resources'], {'requests':declared[actor['name']]})
                checked = json.loads(subprocess.check_output(cli+['launch', result['configuration'], '--prepare-only']))
                self.assertFalse(checked['runtimeStarted'])
                summary = json.loads(subprocess.check_output(cli+['describe',output/'intent.json']))
                rate = summary['shapeRequestsPerSecond']
                if i == 0:
                    starting_rate = rate
                else:
                    for shape in rate:
                        self.assertAlmostEqual(rate[shape], starting_rate[shape], places=6)
        self.assertEqual(checksums(), initial)
