"""Actor-free phase projection, exact terminal proof and changed-input controls."""
import copy
import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import phase_fit as p

MIB = 1024 ** 2


def fixture():
    memory = dict(postgres=512, vault=128, cohort=1024, pgstream=128,
                  admin=256, ui=96, edge=48, provision=256, primer=224)
    result = []
    for name, size in memory.items():
        kind = 'Job' if name in ('provision', 'primer') else 'StatefulSet' if name in ('postgres', 'vault', 'cohort') else 'Deployment'
        budget = {'requests': {'cpu': '100m', 'memory': str(size)+'Mi', 'ephemeral-storage': '16Mi'},
                  'limits': {'cpu': '200m', 'memory': str(size*2)+'Mi', 'ephemeral-storage': '64Mi'}}
        spec = {'nodeName': 'synthetic-node', 'containers': [{'name': name, 'resources': budget}], 'volumes': []}
        obj = {'apiVersion': 'batch/v1' if kind == 'Job' else 'apps/v1', 'kind': kind,
               'metadata': {'name': name, 'namespace': 'ns-synth-phase', 'labels': {'nightscout.org/run-id': 'phase'}},
               'spec': {'replicas': 1, 'template': {'metadata': {}, 'spec': spec}}}
        if name == 'provision':
            obj['spec'].update(backoffLimit=0)
            spec['restartPolicy'] = 'Never'
            spec['initContainers'] = [dict(name=n, resources=copy.deepcopy(budget))
                                      for n in ('wait-stores', 'bootstrap', 'vault-kubernetes-auth')]
            spec['volumes'] = [{'name': 'state', 'emptyDir': {'sizeLimit': '64Mi'}},
                               {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '16Mi'}}]
        spec.update(serviceAccountName='source-account', securityContext={'runAsNonRoot': True})
        spec['volumes'].append({'name': 'source-config', 'secret': {'secretName': 'source-config', 'defaultMode': 288}})
        for container in spec.get('initContainers', []) + spec['containers']:
            container.update(image='synthetic.invalid/source@sha256:'+'1'*64,
                command=['node', 'source.js'], args=['--strict'], workingDir='/app',
                env=[{'name': 'EXPECTED', 'value': 'source'}],
                envFrom=[{'secretRef': {'name': 'source-config'}}],
                volumeMounts=[{'name': 'source-config', 'mountPath': '/run/source', 'readOnly': True}],
                securityContext={'allowPrivilegeEscalation': False})
        result.append(obj)
    return result


def completed(expected):
    job = copy.deepcopy(expected)
    job['metadata']['uid'] = 'job-uid'
    job['status'] = {'succeeded': 1, 'completionTime': 'synthetic-complete',
                     'conditions': [{'type': 'Complete', 'status': 'True', 'lastTransitionTime': 'synthetic-complete'}]}
    pod = {'metadata': {'name': 'provision-one', 'uid': 'pod-uid', 'namespace': expected['metadata']['namespace'],
                       'labels': {'nightscout.org/run-id': 'phase', 'job-name': 'provision'},
                       'ownerReferences': [{'kind': 'Job', 'name': 'provision', 'uid': 'job-uid', 'controller': True}]},
           'spec': copy.deepcopy(p.template(expected)), 'status': {'phase': 'Succeeded'}}
    def state(c):
        return {'name': c['name'], 'containerID': 'synthetic://'+c['name'], 'restartCount': 0,
                'state': {'terminated': {'exitCode': 0, 'finishedAt': 'synthetic-complete'}}}
    pod['status']['containerStatuses'] = [state(c) for c in pod['spec']['containers']]
    pod['status']['initContainerStatuses'] = [state(c) for c in pod['spec']['initContainers']]
    return job, pod


class PhaseFit(unittest.TestCase):
    def setUp(self):
        self.docs = fixture()
        self.env = {'resourceAccounting': 'requests-v1', p.FIELD: {'contract': p.CONTRACT}}
        self.expected = next(o for o in self.docs if p.key(o) == p.PROVISION)

    def test_legacy_is_unchanged_and_opt_in_is_exact(self):
        self.assertIsNone(p.projection({}, self.docs))
        value = {'unmodified': 'legacy'}
        self.assertIs(p.decorate(value, {}, self.docs), value)
        self.assertIs(p.fit_budget({}, value), value)
        for selected in (None, {}, {'contract': p.CONTRACT, 'exclude': 'anything'}, {'contract': 'nearby'}):
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, 'SELECTION'):
                p.projection({p.FIELD: selected}, self.docs)

    def test_exact_projection_keeps_full_requests_and_separate_retained_dimensions(self):
        original = copy.deepcopy(self.docs)
        plan = p.projection(self.env, self.docs)
        node = plan['nodes']['synthetic-node']
        self.assertEqual(node['full']['memoryBytes'], 2672*MIB)
        self.assertEqual(node['phases']['serving']['memoryBytes'], 2416*MIB)
        self.assertEqual(node['retained']['serving']['memoryBytes'], 16*MIB)
        self.assertEqual(node['retained']['serving']['ephemeralBytes'], 64*MIB)
        self.assertEqual(node['peak']['memoryBytes'], 2432*MIB)
        self.assertEqual(node['diskCacheSensitivityBytes'], 64*MIB)
        self.assertEqual(node['peak']['memoryBytes'] + node['diskCacheSensitivityBytes'], 2496*MIB)
        self.assertEqual(self.docs, original)
        full = p.native_budget(node['full'])
        trial = {'requests': full, 'accounted': full, 'placementEnvelopes': {
            'synthetic-node': {'requests': full, 'workloads': node['workloads'], 'podsUpperBound': 9}}}
        decorated = p.decorate(trial, self.env, self.docs)
        self.assertEqual(decorated['requests'], full)
        self.assertEqual(decorated['accounted'], full)
        self.assertEqual(decorated['placementEnvelopes']['synthetic-node']['podsUpperBound'], 9)
        self.assertEqual(p.fit_budget(decorated, full)['memory'], 2432*MIB)

    def test_stage_partition_and_resources_are_bound(self):
        stages = {s: [o for o in self.docs if p.key(o) in names] for s, names in p.PARTITION.items()}
        plan = p.staged_projection(self.env, self.docs, stages)
        self.assertEqual(plan, p.projection(self.env, self.docs))
        broken = copy.deepcopy(stages); broken['serving'].append(copy.deepcopy(self.expected))
        with self.assertRaisesRegex(ValueError, 'STAGE_PARTITION'):
            p.staged_projection(self.env, self.docs, broken)
        broken = copy.deepcopy(stages)
        broken['serving'][0]['spec']['template']['spec']['containers'][0]['resources']['requests']['memory'] = '2Gi'
        with self.assertRaisesRegex(ValueError, 'STAGE_RESOURCES_CHANGED'):
            p.staged_projection(self.env, self.docs, broken)
        self.assertEqual(p.staged_projection(self.env, self.docs, stages), plan)

    def source_mutations(self):
        def first(spec):return spec['initContainers'][0]
        return (('image', lambda spec:first(spec).update(image='synthetic.invalid/changed@sha256:'+'2'*64)),
                ('command', lambda spec:first(spec).update(command=['node', 'changed.js'])),
                ('args', lambda spec:first(spec).update(args=['--changed'])),
                ('regular-image', lambda spec:spec['containers'][0].update(image='changed@sha256:'+'2'*64)),
                ('regular-command', lambda spec:spec['containers'][0].update(command=['changed-command'])),
                ('regular-args', lambda spec:spec['containers'][0].update(args=['--changed'])),
                ('workingDir', lambda spec:first(spec).update(workingDir='/changed')),
                ('env', lambda spec:first(spec)['env'][0].update(value='changed')),
                ('envFrom', lambda spec:first(spec)['envFrom'][0]['secretRef'].update(name='changed')),
                ('mount', lambda spec:first(spec)['volumeMounts'][0].update(mountPath='/changed')),
                ('volume-source', lambda spec:spec['volumes'][-1]['secret'].update(secretName='changed')),
                ('container-security', lambda spec:first(spec)['securityContext'].update(allowPrivilegeEscalation=True)),
                ('pod-security', lambda spec:spec['securityContext'].update(runAsNonRoot=False)),
                ('service-account', lambda spec:spec.update(serviceAccountName='changed')))

    def test_staged_executable_and_source_templates_are_bound_to_original_render(self):
        stages = {s: [copy.deepcopy(o) for o in self.docs if p.key(o) in names] for s, names in p.PARTITION.items()}
        original = p.staged_projection(self.env, self.docs, stages)
        for name, mutate in self.source_mutations():
            with self.subTest(field=name):
                changed = copy.deepcopy(stages); mutate(p.template(changed['provision'][0]))
                with self.assertRaisesRegex(ValueError, 'STAGE_SOURCE_CHANGED'):
                    p.staged_projection(self.env, self.docs, changed)
                self.assertEqual(p.staged_projection(self.env, self.docs, stages), original)
        for stage, docs in stages.items():
            for index, obj in enumerate(docs):
                with self.subTest(workload=p.key(obj)):
                    changed = copy.deepcopy(stages)
                    p.template(changed[stage][index])['containers'][0]['image'] = 'changed@sha256:'+'2'*64
                    with self.assertRaisesRegex(ValueError, 'STAGE_SOURCE_CHANGED'):
                        p.staged_projection(self.env, self.docs, changed)

    def test_live_job_and_pod_executable_and_source_templates_refuse(self):
        job, pod = completed(self.expected)
        for name, mutate in self.source_mutations():
            with self.subTest(field=name, boundary='job'):
                changed = copy.deepcopy(job); mutate(p.template(changed))
                with self.assertRaisesRegex(ValueError, 'JOB_SOURCE_CHANGED'):
                    p.terminal(self.expected, changed, [pod], 'ns-uid', 'phase')
            with self.subTest(field=name, boundary='pod'):
                changed = copy.deepcopy(pod); mutate(changed['spec'])
                with self.assertRaisesRegex(ValueError, 'POD_SOURCE_CHANGED'):
                    p.terminal(self.expected, job, [changed], 'ns-uid', 'phase')
        self.assertEqual(p.terminal(self.expected, job, [pod], 'ns-uid', 'phase')['jobUid'], 'job-uid')

    def test_explicit_api_defaults_and_quantity_normalization_preserve_source(self):
        expected = copy.deepcopy(self.expected)
        for c in p.template(expected).get('initContainers', []) + p.template(expected)['containers']:
            c['env'].append({'name': 'POD_NAMESPACE', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}})
            c['readinessProbe'] = {'exec': {'command': ['test', '-f', '/state/.ready']}}
        job, pod = completed(expected)
        job['spec'].update(parallelism=1, completions=1, completionMode='NonIndexed', suspend=False, manualSelector=False)
        job['metadata'].update(resourceVersion='42', generation=1, managedFields=[{'manager': 'kube-controller-manager'}])
        job['spec']['template']['metadata']['labels'] = {'batch.kubernetes.io/controller-uid': 'job-uid'}
        pod['metadata'].update(resourceVersion='43', annotations={'server-metadata': 'allowed'})
        for spec in (p.template(job), pod['spec']):
            spec.update(dnsPolicy='ClusterFirst', schedulerName='default-scheduler',
                        terminationGracePeriodSeconds=30, enableServiceLinks=True,
                        priority=0, preemptionPolicy='PreemptLowerPriority', serviceAccount='source-account',
                        tolerations=[{'key': 'node.kubernetes.io/'+reason, 'operator': 'Exists',
                                      'effect': 'NoExecute', 'tolerationSeconds': 300}
                                     for reason in ('not-ready', 'unreachable')])
            for c in spec.get('initContainers', []) + spec['containers']:
                c.update(terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File',
                         imagePullPolicy='IfNotPresent')
                c['readinessProbe'].update(failureThreshold=3, successThreshold=1, timeoutSeconds=1,
                                           periodSeconds=10, initialDelaySeconds=0)
                c['env'][-1]['valueFrom']['fieldRef']['apiVersion'] = 'v1'
                c['envFrom'][0]['secretRef']['optional'] = False
                for group in c['resources'].values():
                    group['cpu'] = str(p.resource_budget.quantity(group['cpu'], True, p.require)/1000)
                    group['memory'] = str(p.resource_budget.quantity(group['memory'], False, p.require))
            spec['volumes'][-1]['secret']['optional'] = False
            spec['volumes'][0]['emptyDir']['medium'] = ''
            spec['volumes'][0]['emptyDir']['sizeLimit'] = str(64*MIB)
        proof = p.terminal(expected, job, [pod], 'ns-uid', 'phase')
        self.assertEqual(proof['sourceTemplateSha256'], p.digest(expected['spec']['template']))
        self.assertEqual(proof, p.terminal(expected, job, [pod], 'ns-uid', 'phase', proof))
        changed = copy.deepcopy(job);p.template(changed)['schedulerName'] = 'changed-scheduler'
        with self.assertRaisesRegex(ValueError, 'JOB_SOURCE_CHANGED'):
            p.terminal(expected, changed, [pod], 'ns-uid', 'phase')

    def test_only_the_existing_service_account_admission_projection_is_permitted(self):
        expected = copy.deepcopy(self.expected);p.template(expected)['automountServiceAccountToken'] = True
        job, pod = completed(expected)
        name = 'kube-api-access-synthetic'
        pod['spec']['volumes'].append({'name': name, 'projected': {'defaultMode': 420, 'sources': [
            {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
            {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
            {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}})
        for c in pod['spec'].get('initContainers', []) + pod['spec']['containers']:
            c['volumeMounts'].append({'name': name, 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True})
        p.terminal(expected, job, [pod], 'ns-uid', 'phase')
        changed = copy.deepcopy(pod);changed['spec']['containers'][0]['volumeMounts'][-1]['mountPath'] = '/run/source'
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_ADMISSION_VOLUME'):
            p.terminal(expected, job, [changed], 'ns-uid', 'phase')
        disabled = copy.deepcopy(expected);p.template(disabled)['automountServiceAccountToken'] = False
        no_mount_job, _ = completed(disabled)
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_ADMISSION_VOLUME'):
            p.terminal(disabled, no_mount_job, [pod], 'ns-uid', 'phase')

    def test_job_policy_and_unknown_workload_refuse(self):
        for mutate in (lambda j: j['spec'].update(parallelism=2), lambda j: j['spec'].update(completions=2),
                       lambda j: j['spec'].update(backoffLimit=1),
                       lambda j: p.template(j).update(restartPolicy='OnFailure'),
                       lambda j: p.template(j).update(ephemeralContainers=[{'name': 'unexpected'}]),
                       lambda j: p.template(j)['initContainers'][0].update(restartPolicy='Always')):
            docs = copy.deepcopy(self.docs); job = next(o for o in docs if p.key(o) == p.PROVISION); mutate(job)
            with self.assertRaises(ValueError):p.projection(self.env, docs)
        with self.assertRaisesRegex(ValueError, 'WORKLOAD_PARTITION'):
            p.projection(self.env, self.docs+[copy.deepcopy(self.expected)])

    def test_terminal_proof_covers_every_container_and_stays_monotonic(self):
        job, pod = completed(self.expected)
        proof = p.terminal(self.expected, job, [pod], 'ns-uid', 'phase')
        self.assertEqual(len(proof['pod']['containers']), 4)
        self.assertEqual(p.terminal(self.expected, job, [pod], 'ns-uid', 'phase', proof), proof)
        self.assertEqual(p.terminal(self.expected, job, [], 'ns-uid', 'phase', proof), proof)
        with self.assertRaisesRegex(ValueError, 'TERMINAL_PROOF_MISSING'):
            p.terminal(self.expected, job, [], 'ns-uid', 'phase')
        for mutate in (lambda j: j['metadata'].update(uid='replacement'),
                       lambda j: j['status'].update(completionTime='changed')):
            changed = copy.deepcopy(job); mutate(changed)
            with self.assertRaisesRegex(ValueError, 'TERMINAL_PROOF_CHANGED'):
                p.terminal(self.expected, changed, [], 'ns-uid', 'phase', proof)

    def test_incomplete_failed_terminating_and_overlapping_jobs_refuse(self):
        job, pod = completed(self.expected)
        for mutate in (lambda j: j['status'].update(conditions=[]), lambda j: j['status'].update(active=1),
                       lambda j: j['status'].update(failed=1), lambda j: j['status'].update(terminating=1),
                       lambda j: j['metadata'].update(deletionTimestamp='deleting')):
            changed = copy.deepcopy(job); mutate(changed)
            with self.assertRaises(ValueError):p.terminal(self.expected, changed, [pod], 'ns-uid', 'phase')
        with self.assertRaisesRegex(ValueError, 'PROVISION_POD_ROSTER'):
            p.terminal(self.expected, job, [pod, copy.deepcopy(pod)], 'ns-uid', 'phase')
        self.assertEqual(p.terminal(self.expected, job, [pod], 'ns-uid', 'phase')['jobUid'], 'job-uid')

    def test_restarted_running_changed_uid_or_volume_pod_refuses_and_restores(self):
        job, pod = completed(self.expected)
        proof = p.terminal(self.expected, job, [pod], 'ns-uid', 'phase')
        for mutate in (lambda v: v['status'].update(phase='Running'),
                       lambda v: v['status']['containerStatuses'][0].update(restartCount=1),
                       lambda v: v['status']['initContainerStatuses'][-1]['state']['terminated'].update(exitCode=1),
                       lambda v: v['status']['containerStatuses'][0]['state'].update(running={}),
                       lambda v: v['status']['containerStatuses'][0].update(containerID='replacement'),
                       lambda v: v['metadata'].update(uid='replacement'),
                       lambda v: v['metadata'].update(deletionTimestamp='deleting'),
                       lambda v: v['spec'].update(ephemeralContainers=[{'name': 'unexpected'}]),
                       lambda v: v['status'].update(ephemeralContainerStatuses=[{'name': 'unexpected'}]),
                       lambda v: v['spec']['volumes'][1]['emptyDir'].update(sizeLimit='32Mi')):
            changed = copy.deepcopy(pod); mutate(changed)
            with self.assertRaises(ValueError):p.terminal(self.expected, job, [changed], 'ns-uid', 'phase', proof)
            self.assertEqual(p.terminal(self.expected, job, [pod], 'ns-uid', 'phase', proof), proof)

    def test_runtime_receipt_plan_and_live_job_are_positive_boundaries(self):
        job, pod = completed(self.expected)
        plan = p.projection(self.env, self.docs)
        proof = p.terminal(self.expected, job, [pod], 'ns-uid', 'phase')
        proof['planSha256'] = p.digest(plan)
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'retirement.json';path.write_text(json.dumps(proof))
            ref = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            c = {'runId': 'phase', 'resourceAccounting': 'requests-v1', p.FIELD: {'plan': plan, 'retirement': ref}}
            objects = {p.key(o): o for o in self.docs}
            self.assertEqual(p.runtime(c, objects, 'ns-uid', job, [pod])['retirement'], 'VERIFIED')
            changed = copy.deepcopy(pod); changed['status']['containerStatuses'][0]['restartCount'] = 1
            with self.assertRaises(ValueError):p.runtime(c, objects, 'ns-uid', job, [changed])
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'RECEIPT_CHANGED'):p.runtime(c, objects, 'ns-uid', job, [pod])
            path.write_text(json.dumps(proof))
            self.assertEqual(p.runtime(c, objects, 'ns-uid', job, [])['podPresent'], False)
            altered = copy.deepcopy(c); altered[p.FIELD]['plan']['nodes']['synthetic-node']['peak']['memoryBytes'] -= 1
            with self.assertRaisesRegex(ValueError, 'RUNTIME_PLAN_CHANGED'):
                p.runtime(altered, objects, 'ns-uid', job, [pod])

    def test_actual_lifecycle_checks_terminal_proof_before_allocating_later_roles(self):
        source = Path(__file__).with_name('lifecycle.py')
        tree = ast.parse(source.read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('install', 'confirm_provision_retirement')]
        with TemporaryDirectory() as tmp:
            job, pod = completed(self.expected)
            made = []
            later = next(o for o in self.docs if p.key(o) == 'Deployment/admin')
            by_stage = {'provision': [self.expected], 'private-admin': [later]}
            live = Path(tmp)
            state = {'job': job, 'pods': [pod]}
            def create(obj):
                made.append(p.key(obj))
                return {**copy.deepcopy(obj), 'metadata': {**obj['metadata'], 'uid': 'later-uid'}}
            scope = {'cfg': {'resourcePhasePreflight': {'plan': p.projection(self.env, self.docs)}},
                     'phase_fit': p, 'ns': 'ns-synth-phase', 'nsuid': 'ns-uid', 'rid': 'phase',
                     'live': live, 'uids': [{'kind': 'Job', 'name': 'provision', 'uid': 'job-uid'}],
                     'step': lambda stage: None, 'owned': lambda: None,
                     'objects': lambda stage: by_stage[stage], 'get': lambda *args: state['job'],
                     'pods': lambda label: [row for row in state['pods'] if not label or
                                            row['metadata'].get('labels', {}).get('job-name') == 'provision'],
                     'create': create,
                     'read': lambda path: json.loads(path.read_text()),
                     'put': lambda name, value: (live/name).write_text(json.dumps(value))}
            exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), scope)
            state['job'] = copy.deepcopy(job);state['job']['status']['active'] = 1
            with self.assertRaisesRegex(ValueError, 'JOB_NOT_COMPLETE'):
                scope['install']('private-admin')
            self.assertEqual(made, [])
            state['job'] = job
            overlap = copy.deepcopy(pod)
            overlap['metadata'].update(name='overlapping-unlabelled', uid='overlap-uid')
            overlap['metadata']['labels'].pop('job-name')
            overlap['status']['phase'] = 'Running'
            state['pods'] = [pod, overlap]
            with self.assertRaisesRegex(ValueError, 'PROVISION_POD_ROSTER'):
                scope['install']('private-admin')
            self.assertEqual(made, [])
            state['pods'] = [pod]
            for name, mutate in self.source_mutations():
                with self.subTest(field=name):
                    state['job'] = copy.deepcopy(job);state['pods'] = [copy.deepcopy(pod)]
                    mutate(p.template(state['job']));mutate(state['pods'][0]['spec'])
                    with self.assertRaisesRegex(ValueError, 'JOB_SOURCE_CHANGED'):
                        scope['install']('private-admin')
                    self.assertEqual(made, [])
                    self.assertFalse((live/'provision-retirement.json').exists())
            state['job'] = job;state['pods'] = [pod]
            scope['install']('private-admin')
            self.assertEqual(made, ['Deployment/admin'])
            self.assertTrue((live/'provision-retirement.json').is_file())
            state['pods'] = []
            scope['confirm_provision_retirement']()
            state['job'] = copy.deepcopy(job);state['job']['metadata']['uid'] = 'replaced'
            with self.assertRaisesRegex(AssertionError, 'JOB_UID_CHANGED'):
                scope['confirm_provision_retirement']()

    def test_actual_adapter_observe_cannot_skip_the_runtime_phase_guard(self):
        from test_adapter import fixture as adapter_fixture, k
        import phase_source_private
        c, inventory, rendered, client = adapter_fixture()
        objects = k.validate(c, inventory, rendered)
        c[p.FIELD] = {'selected': 'deliberate wiring control'}
        with patch.object(phase_source_private, 'observe', side_effect=ValueError('K8S_PHASE_TEST_TERMINAL_REFUSAL')) as guard:
            # Runtime source equality now uses its scoped private proof port;
            # a refused proof remains an entry refusal before any driver.
            with self.assertRaisesRegex(k.Refused, 'PHASE_PRIVATE_PROOF_UNAVAILABLE'):
                k.observe(c, objects, client)
            guard.assert_called_once()
        c.pop(p.FIELD)
        self.assertEqual(k.observe(c, objects, client)['runId'], c['runId'])


if __name__ == '__main__':unittest.main()
