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


class CandidateParameters(unittest.TestCase):
    def test_candidate_is_resolved_from_image_parameters_not_receipts(self):
        import standard_case
        digest = 'registry.test/app@sha256:' + '1'*64
        spec = {'Id': 'sha256:' + '2'*64, 'Config': {'Labels': {'org.opencontainers.image.revision': 'a'*40,
                                                               'org.nightscout.deploy.revision': 'b'*40}}}
        value = standard_case.resolve_image(digest, lambda ref: spec)
        self.assertEqual(value, {'reference': digest, 'imageId': 'sha256:'+'2'*64, 'core': 'a'*40, 'deploy': 'b'*40})
        with self.assertRaisesRegex(k.Refused, 'STANDARD_IMAGE_DIGEST_REQUIRED'):
            standard_case.resolve_image('registry.test/app:latest', lambda ref: spec)

    def test_frozen_source_reads_the_candidate(self):
        import frozen
        candidate = {'app': 'r/app@sha256:'+'1'*64, 'appImageId': 'sha256:'+'2'*64,
                     'postgres': 'r/pg@sha256:'+'3'*64, 'postgresImageId': 'sha256:'+'4'*64,
                     'coreCommit': 'a'*40, 'deployCommit': 'b'*40}
        manifest = {'version': 1, 'kind': 'k8s-frozen-experiment', 'bindingCommit': 'b'*40, 'candidate': candidate}
        self.assertEqual(frozen.source(manifest), {'coreCommit': 'a'*40, 'deployCommit': 'b'*40,
                                                   'localImageId': 'sha256:'+'2'*64, 'sourceAcceptance': 'PENDING'})
        with self.assertRaisesRegex(frozen.Refused, 'CANDIDATE'):
            frozen.source({**manifest, 'candidate': {**candidate, 'app': 'r/app:tag'}})


class StandardCase(unittest.TestCase):
    @unittest.skipUnless(all(os.environ.get('K8S_STANDARD_' + key) for key in
                             ('TEMPLATE', 'BINDING', 'PROFILE', 'APP_IMAGE')), 'needs a template case, a deploy checkout and a local candidate image')
    def test_public_cli_prepares_two_points_without_source_writes_or_historical_capacity(self):
        paths = {key:Path(os.environ['K8S_STANDARD_' + key]).resolve()
                 for key in ('TEMPLATE', 'BINDING', 'PROFILE')}
        app_image = os.environ['K8S_STANDARD_APP_IMAGE']
        template = paths['TEMPLATE']
        inputs = [template/name for name in ('intent.json','environment.json','lifecycle-input.json',
                                             'binding-inputs.json','native-run-template.json')]
        inputs += list((template/'stages').glob('*.json'))
        inputs += [paths['PROFILE']]
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
                cmd = cli + ['standard', template, paths['BINDING'], selected, output, '--app-image', app_image,
                             '--namespace-prefix', 'smoke-']
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
                quota, = [obj for obj in objs if obj['kind']=='ResourceQuota']
                limits, = [obj for obj in objs if obj['kind']=='LimitRange']
                floor, = limits['spec']['limits']
                self.assertTrue(floor['defaultRequest'])
                self.assertNotIn('default', floor)
                totals = dict.fromkeys(('millicpus','memoryBytes','ephemeralBytes'), 0)
                replicas = 0
                for obj in objs:
                    if obj['kind'] in k.WORKLOADS:
                        count = obj['spec'].get('replicas',obj['spec'].get('parallelism',1))
                        replicas += count
                        budget = k.resource_budget.pod_budget(k.template(obj)['spec'],'requests-v1',k.need)
                        for key in totals:
                            totals[key] += count*budget[key]
                hard = quota['spec']['hard']
                self.assertGreaterEqual(int(hard['pods']), 2*replicas)
                for key, field in [('millicpus','cpu'),('memoryBytes','memory'),('ephemeralBytes','ephemeral-storage')]:
                    self.assertGreaterEqual(k.resource_budget.quantity(hard['requests.'+field],field=='cpu',k.need),
                                            2*totals[key])
                for obj in objs:
                    if obj['kind'] in k.WORKLOADS:
                        pod = k.template(obj)['spec']
                        self.assertFalse(any(pod.get(key) for key in ('nodeName','nodeSelector','affinity')))
                        self.assertEqual(pod.get('tolerations',[]), [{'key':'worker','value':'reserved',
                                         'operator':'Equal','effect':'NoSchedule'}] if taint else [])
                job, = [o for o in objs if o['kind']=='Job' and o['metadata']['name']=='k6']
                load_actor, = [a for a in job['spec']['template']['spec']['containers'] if a['name']=='k6']
                target, = [x['value'] for x in load_actor['env'] if x['name']=='BASE_URL']
                edge, = [o for o in objs if o['kind']=='Service' and o['metadata']['name']=='edge']
                self.assertIn(target, ['http://edge:'+str(port['port']) for port in edge['spec']['ports']])
                for obj in objs:
                    if obj['kind']=='Deployment':
                        pod = k.template(obj)['spec']
                        self.assertNotIn('wait-for-jobs',[actor['name'] for actor in pod.get('initContainers',[])])
                        for actor in pod['containers']:
                            if actor['name'] in ('api','evaluator','realtime','tenant-admin'):
                                self.assertEqual(actor['readinessProbe']['exec'],actor['livenessProbe']['exec'])
                                self.assertEqual(actor['readinessProbe']['exec'],actor['startupProbe']['exec'])
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
