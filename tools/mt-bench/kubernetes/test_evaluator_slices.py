"""Evaluator K>1 (binding slices.evaluator): census, progress per ordinal, readiness, seed K and
fixture K, and the reader's detach wait. Synthetic replies only; no cluster."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_adapter import fixture, iso, A, B
from test_progress_capture import Clock, R, S
import kube_adapter as k
import execute
import fixture as reader
import fixture_copy
import producer_startup


def sliced(count):
    """test_adapter's fixture with the evaluator as its own StatefulSet of `count` Pods."""
    c, inv, rendered, client = fixture()
    labels = {c['ownerLabel']: c['runId']}
    cohort = rendered[1]
    container = next(x for x in cohort['spec']['template']['spec']['containers'] if x['name'] == 'evaluator')
    sts = {'apiVersion': 'apps/v1', 'kind': 'StatefulSet',
           'metadata': {'name': 'evaluator', 'namespace': c['namespace'], 'labels': dict(labels)},
           'spec': {'replicas': count, 'template': {'metadata': {'labels': dict(labels)},
                                                   'spec': {'containers': [copy.deepcopy(container)]}}}}
    rendered.append(sts)
    c['roles']['evaluator'] = {'workload': 'StatefulSet/evaluator', 'container': 'evaluator'}
    actual = copy.deepcopy(sts)
    actual['metadata'].update(uid='uid-evaluator', resourceVersion='10')
    client.objects['StatefulSet/evaluator'] = actual
    template = next(p for p in client.pods if p['metadata']['name'] == 'cohort-0')
    for i in range(count):
        pod = copy.deepcopy(template)
        pod['metadata'].update(name='evaluator-%d' % i, uid='uid-evaluator-%d' % i,
                               ownerReferences=[{'kind': 'StatefulSet', 'name': 'evaluator', 'uid': 'uid-evaluator', 'controller': True}])
        pod['spec'] = copy.deepcopy(sts['spec']['template']['spec'])
        pod['spec']['nodeName'] = 'synthetic-node'
        pod['status']['containerStatuses'] = [dict(template['status']['containerStatuses'][0], name='evaluator',
                                                   containerID='containerd://evaluator-%d' % i)]
        client.pods.append(pod)
    return c, inv, rendered, client


class Census(unittest.TestCase):
    def test_every_evaluator_pod_is_counted_and_placed(self):
        c, inv, rendered, client = sliced(2)
        objects = k.validate(c, inv, rendered)
        observed = k.observe(c, objects, client)
        self.assertEqual([n for n, _ in k.role_pods(c, observed, 'evaluator')], ['evaluator-0', 'evaluator-1'])
        self.assertEqual({observed['pods'][n]['nodeName'] for n in ('evaluator-0', 'evaluator-1')}, {'synthetic-node'})
        # One ordinal missing: the census refuses instead of measuring half the role.
        client.pods = [p for p in client.pods if p['metadata']['name'] != 'evaluator-1']
        with self.assertRaisesRegex(k.Refused, 'ROLE_POD_UNMEASURED:evaluator'):
            k.observe(c, objects, client)
        # A single-Pod role selector still refuses K>1, and other workloads keep one Pod.
        with self.assertRaisesRegex(k.Refused, 'ROLE_NOT_READY'):
            k.selected_pod(c, observed, 'evaluator')
        rendered[-1]['spec']['replicas'] = 0
        with self.assertRaisesRegex(k.Refused, 'WORKLOAD_REPLICAS_INVALID:StatefulSet/evaluator'):
            k.validate(c, inv, rendered)

    def test_every_workload_counts_one_pod_per_replica(self):
        # api as a Deployment of 2 and realtime as a StatefulSet of 2: each Pod is counted and placed.
        # Red before: any workload but the evaluator refused replicas>1 (WORKLOAD_REPLICA_CENSUS_UNSUPPORTED).
        c, inv, rendered, client = sliced(1)
        labels = {c['ownerLabel']: c['runId']}
        cohort = rendered[1]
        template = next(p for p in client.pods if p['metadata']['name'] == 'cohort-0')
        def add(kind, name, count, controller):
            container = next(x for x in cohort['spec']['template']['spec']['containers'] if x['name'] == name)
            obj = {'apiVersion': 'apps/v1', 'kind': kind, 'metadata': {'name': name, 'namespace': c['namespace'], 'labels': dict(labels)},
                   'spec': {'replicas': count, 'template': {'metadata': {'labels': dict(labels)},
                                                           'spec': {'containers': [copy.deepcopy(container)]}}}}
            rendered.append(obj)
            c['roles'][name] = {'workload': kind + '/' + name, 'container': name}
            actual = copy.deepcopy(obj); actual['metadata'].update(uid='uid-' + name, resourceVersion='10')
            client.objects[kind + '/' + name] = actual
            for i in range(count):
                pod = copy.deepcopy(template)
                pod['metadata'].update(name='%s-%s' % (name, i if kind == 'StatefulSet' else 'h%d' % i), uid='uid-%s-%d' % (name, i),
                                       ownerReferences=[controller(i)])
                pod['spec'] = copy.deepcopy(obj['spec']['template']['spec']); pod['spec']['nodeName'] = 'synthetic-node'
                pod['status']['containerStatuses'] = [dict(template['status']['containerStatuses'][0], name=name,
                                                           containerID='containerd://%s-%d' % (name, i))]
                client.pods.append(pod)
        add('StatefulSet', 'realtime', 2, lambda i: {'kind': 'StatefulSet', 'name': 'realtime', 'uid': 'uid-realtime', 'controller': True})
        rs = {'apiVersion': 'apps/v1', 'kind': 'ReplicaSet', 'metadata': {'name': 'api-h', 'uid': 'uid-rs-api', 'labels': dict(labels), 'namespace': c['namespace'],
              'ownerReferences': [{'kind': 'Deployment', 'name': 'api', 'uid': 'uid-api', 'controller': True}]}}
        original_get = client.get
        def get(kind, name=None, cleanup=False):
            if kind == 'replicasets' and name is None:
                return {'items': [rs]}
            return original_get(kind, name, cleanup) if name is not None else original_get(kind, cleanup=cleanup)
        client.get = get
        add('Deployment', 'api', 2, lambda i: {'kind': 'ReplicaSet', 'name': 'api-h', 'uid': 'uid-rs-api', 'controller': True})
        objects = k.validate(c, inv, rendered)
        observed = k.observe(c, objects, client)
        for role, count in (('api', 2), ('realtime', 2), ('evaluator', 1)):
            self.assertEqual(len(k.role_pods(c, observed, role)), count, role)
        client.pods = [p for p in client.pods if p['metadata']['name'] != 'api-h1']
        with self.assertRaisesRegex(k.Refused, 'ROLE_POD_UNMEASURED:api'):
            k.observe(c, objects, client)

    def test_k1_census_unchanged(self):
        c, inv, rendered, client = sliced(1)
        observed = k.observe(c, k.validate(c, inv, rendered), client)
        self.assertEqual(k.selected_pod(c, observed, 'evaluator'), ('evaluator-0', 'evaluator'))
        self.assertEqual(k.evaluator_services(1), ['evaluator'])

    def test_readiness_waits_for_every_replica(self):
        one, two = ('uid-0', (('evaluator', 0),)), ('uid-1', (('evaluator', 0),))
        self.assertIsNone(producer_startup.replica_identity([one], 2))
        self.assertEqual(producer_startup.replica_identity([two, one], 2), (one, two))


# Core lib/pool-membership/slice.js bucket(id, K) for K = 1..8, computed with core 6da24edbb7.
CORE_BUCKETS = {
    '11111111-1111-4111-8111-111111111111': [0, 0, 1, 0, 0, 4, 0, 4],
    '22222222-2222-4222-8222-222222222222': [0, 1, 0, 3, 2, 3, 0, 3],
    '33333333-3333-4333-8333-333333333333': [0, 1, 1, 3, 1, 1, 3, 7],
    '44444444-4444-4444-8444-444444444444': [0, 0, 0, 0, 4, 0, 3, 4],
    '55555555-5555-4555-8555-555555555555': [0, 1, 0, 1, 2, 3, 1, 5],
    '66666666-6666-4666-8666-666666666666': [0, 1, 0, 1, 3, 3, 5, 5],
    '0f0e0d0c-0b0a-4908-8706-050403020100': [0, 0, 1, 0, 1, 4, 6, 4],
    'ffffffff-ffff-4fff-bfff-ffffffffffff': [0, 0, 1, 0, 0, 4, 5, 0],
}


def static_page(ordinal, count, runtime, selected, completed=1):
    """One slice's inspection page, as core answers it: only for tenants it owns."""
    rows = [{'tenant': tenant, 'admitted': True, 'ready': True, 'code': None, 'evaluation': {'alert': None},
             'cycles': completed, 'progress': {'generation': 1, 'completedAcquisitions': completed, 'completedTimeCycles': 0,
                                               'failedCompletions': 0, 'lastCompletedAgeMs': 1},
             'jobs': dict.fromkeys(k.evaluator_progress.JOB_FLAGS, False), 'dueAt': None, 'dueReason': None}
            for tenant in selected]
    configured = {'ordinal': ordinal, 'mode': 'static', 'count': count, 'rule': 'sha256-modulo-v1', 'leaseMs': None}
    return {'selected': list(selected), 'selfOrdinal': ordinal, 'selfMode': 'static', 'selfCount': count,
            'view': {'kind': 'evaluator', 'runtimeId': runtime, 'configured': configured, 'observed': None,
                     'gate': {'eligible': True, 'reason': None, 'members': count}, 'tenants': rows}}


def slice_pod(count, runtimes, targets, completed=lambda: 1):
    """kubectl exec into evaluator-<i>: core refuses a selector naming a tenant the slice does not own
    (evaluator-inspection.js:22-25), which the transport answers as 503 and the helper as exit 1."""
    def call(args, data=b'', **kwargs):
        pod = args[2]; ordinal = int(pod.rsplit('-', 1)[1])
        targets.append(pod)
        prefix = data.decode().split(';', 1)[0]
        selected = json.loads(prefix.removeprefix('const M7_PROGRESS_IDS='))
        if any(k.evaluator_progress.bucket(t, count) != ordinal for t in selected):
            raise k.Refused('K8S_EXEC_FAILED')
        raw = json.dumps(static_page(ordinal, count, runtimes[ordinal], selected, completed())).encode() + b'\n'
        sink = kwargs.get('response_sink')
        if sink: sink(raw, 0)
        return raw
    return call


class SliceRule(unittest.TestCase):
    def test_bucket_matches_core(self):
        for tenant, expected in CORE_BUCKETS.items():
            self.assertEqual([k.evaluator_progress.bucket(tenant, n) for n in range(1, 9)], expected, tenant)

    def test_partition_covers_each_id_once_and_k1_asks_everyone(self):
        ids = sorted(CORE_BUCKETS)
        shares = k.evaluator_progress.partition(['evaluator', 'evaluator-2'], ids)
        self.assertEqual(sorted(t for v in shares.values() for t in v), ids)
        self.assertEqual(shares['evaluator-2'], [t for t in ids if CORE_BUCKETS[t][1] == 1])
        with self.assertRaisesRegex(k.evaluator_progress.Refused, 'SLICE_EMPTY'):
            k.evaluator_progress.partition(['evaluator', 'evaluator-2'], ['11111111-1111-4111-8111-111111111111'])
        seen = {}
        def fetch(service, chosen, queries, budget):
            seen[service] = chosen
            return json.dumps(static_page(0, 1, R, chosen)).encode()
        k.evaluator_progress.round_view(['evaluator'], ids, fetch, demand_driven=True, sliced=True)
        self.assertEqual(seen, {'evaluator': ids})


class Progress(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name); self.out = self.d/'load'; self.out.mkdir()
        self.c, inv, rendered, self.client = sliced(2)
        self.clock = Clock()
        self.c.update(tenants=2, tier='discovery')
        self.c['deadlines'] = {'workUntil': iso(self.clock.now+7200), 'cleanupUntil': iso(self.clock.now+7800)}
        self.objects = k.validate(self.c, inv, rendered)
        self.baseline = k.observe(self.c, self.objects, self.client)
        self.targets = []; self.done = [0]
        self.client.call = Mock(side_effect=slice_pod(2, (R, S), self.targets, lambda: self.done[0]))
        self.roster = [{'id': t, 'token': 'synthetic', 'host': 'synthetic.test'} for t in (A, B)]

    def read(self, name):
        with patch.object(k.time, 'time', self.clock.time), patch.object(k, 'active_baseline', return_value=self.baseline), \
             patch.object(execute, 'roster', return_value=self.roster):
            return execute.retained_progress(self.d, self.out, self.c, self.objects, self.client, name)

    def test_each_ordinal_is_asked_only_for_its_share(self):
        # Red before the sliced read: every ordinal was asked for every id, each refused, UNMEASURED.
        value = self.read('progress-before')
        self.assertIsNotNone(value, (self.out/'progress-before-failure.json').read_text() if (self.out/'progress-before-failure.json').exists() else '')
        self.assertEqual(sorted(self.targets), ['evaluator-0', 'evaluator-1'])
        self.assertEqual({s: v['ordinal'] for s, v in value['instances'].items()}, {'evaluator': 0, 'evaluator-2': 1})
        self.assertEqual({t: v['service'] for t, v in value['owners'].items()}, {A: 'evaluator', B: 'evaluator-2'})
        self.assertEqual(value['slices'], {'rule': 'sha256-modulo-v1', 'count': 2})
        first = k.document(self.out/'progress-before-response.json')
        second = k.document(self.out/'progress-before-evaluator-2-response.json')
        self.assertEqual((first['podUid'], second['podUid']), ('uid-evaluator-0', 'uid-evaluator-1'))
        self.assertTrue((self.out/'progress-before.private.jsonl').is_file() and (self.out/'progress-before-evaluator-2.private.jsonl').is_file())

    def test_three_rounds_assess_with_shares_covering_every_id_once(self):
        for name in ('progress-before', 'progress-midpoint', 'progress-after'):
            self.assertIsNotNone(self.read(name), name)
            self.done[0] += 1
        result = execute.assess_progress(self.out, self.c, [A, B])
        self.assertEqual((result['verdict'], result['tenants'], result['completedWorkDelta']), ('PASS', 2, 4))
        # A round whose shares overlap or miss an id is a coverage failure, not a pass.
        rounds = [k.document(self.out/(n+'.json')) for n in ('progress-before', 'progress-midpoint', 'progress-after')]
        broken = copy.deepcopy(rounds)
        broken[2]['allRows']['evaluator'][B] = broken[2]['allRows']['evaluator-2'].pop(B)
        with self.assertRaisesRegex(k.evaluator_progress.Refused, 'COVERAGE'):
            k.evaluator_progress.assess(broken, [A, B], 'load', demand_driven=True)


class Bound(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('NS_DEPLOY_DIR'), 'NS_DEPLOY_DIR unset: the deploy tree holds the bound')
    def test_progress_reader_bound_equals_the_deploy_bound(self):
        # One evaluator K bound: deploy bindings/compose/multitenant/evaluator-workers.js MAX_WORKERS
        # (its own tests hold the Kubernetes assert and input schema to it).
        module = Path(os.environ['NS_DEPLOY_DIR'])/'bindings/compose/multitenant/evaluator-workers.js'
        value = subprocess.run(['node', '-e', 'process.stdout.write(String(require(process.argv[1]).MAX_WORKERS))', str(module)],
                               check=True, capture_output=True, text=True).stdout
        self.assertEqual(int(value), k.evaluator_progress.POLICY['maxInstances'])


class ProgressRoster(unittest.TestCase):
    def test_compose_names_cover_1_to_32_and_refuse_beyond(self):
        ordinal = k.evaluator_progress.service_ordinal
        self.assertEqual([ordinal(s) for s in ('evaluator', 'evaluator-2', 'evaluator-20', 'evaluator-32')], [0, 1, 19, 31])
        for bad in ('evaluator-1', 'evaluator-33', 'evaluator-02', 'evaluator-0'):
            with self.assertRaises(k.evaluator_progress.Refused):
                ordinal(bad)
        self.assertEqual(k.evaluator_progress.POLICY['maxInstances'], 32)


class SeedAndFixtureK(unittest.TestCase):
    def test_seed_environment_follows_the_binding(self):
        writer = {'NS_INPUT_TRANSPORT': 'writer-driven'}
        k1 = {'inputTransport': 'writer-driven', 'seed': {'environment': writer}}
        self.assertEqual(fixture_copy.seed_environment(k1), writer)
        k2 = {'inputTransport': 'writer-driven', 'slices': {'evaluator': 2},
              'seed': {'environment': {'NS_EVALUATOR_WORKERS': '2', **writer}}}
        self.assertEqual(fixture_copy.seed_environment(k2), {'NS_EVALUATOR_WORKERS': '2', **writer})
        with self.assertRaisesRegex(fixture_copy.Refused, 'SEED_EVALUATOR_SLICES'):
            fixture_copy.seed_environment({'inputTransport': 'writer-driven', 'slices': {'evaluator': 2}, 'seed': {'environment': writer}})
        with self.assertRaisesRegex(fixture_copy.Refused, 'SEED_INPUT_TRANSPORT'):
            fixture_copy.seed_environment({'seed': {'environment': {}}})
        self.assertEqual(fixture_copy.slices_record(k1), {'inputTransport': 'writer-driven'})
        self.assertEqual(fixture_copy.slices_record(k2), {'evaluatorSlices': 2, 'inputTransport': 'writer-driven'})

    def test_a_writer_driven_fixture_restores_at_any_k(self):
        # K-free (decision statefulset-ordinal-scaling, amended): the seed's K is not a restore refusal.
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)/'fixture'; directory.mkdir(mode=0o700)
        parts = fixture_copy.PARTS
        manifest = {'version': 1, 'handles': dict.fromkeys(parts, 'h'), 'sizes': dict.fromkeys(parts, '1Gi'),
                    'driver': 'dobs.csi.digitalocean.com', 'tenants': 1000, 'postgresImage': 'pg',
                    'snapshotClass': 's', 'storageClass': 'c', 'inputTransport': 'writer-driven'}
        for name, value in ((fixture_copy.MANIFEST, manifest), (fixture_copy.SECRETS, [])):
            (directory/name).write_text(json.dumps(value)); (directory/name).chmod(0o600)
        chosen = {'mode': 'restore', 'directory': str(directory)}
        never = '/nonexistent/jsonnet'  # passing the checks proceeds to the renderer
        for seeded, restored in ((1, 2), (2, 1), (2, 2)):
            manifest['evaluatorSlices'] = seeded
            (directory/fixture_copy.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaises(FileNotFoundError):
                fixture_copy.render(never, '/nonexistent', 'ns', 'run', chosen, 1000, 'pg', restored)
        with self.assertRaisesRegex(fixture_copy.Refused, 'TENANTS_CHANGED'):
            fixture_copy.render(never, '/nonexistent', 'ns', 'run', chosen, 999, 'pg', 1)


class ReaderDetach(unittest.TestCase):
    def run_wait(self, attachments_per_read, seconds=90):
        clock = Clock()
        reads = iter(attachments_per_read)
        calls = []
        def run(args, **kwargs):
            calls.append(args[:2])
            if args[1] == 'pvc':
                return subprocess.CompletedProcess(args, 0, b'pvc-123')
            names = next(reads)
            items = [{'metadata': {'name': n}, 'spec': {'source': {'persistentVolumeName': v}}} for n, v in names]
            return subprocess.CompletedProcess(args, 0, json.dumps({'items': items}).encode())
        return reader.wait_detached(run, 'fixture-primer-results', clock.now + 3600, seconds, clock), calls

    def test_reader_waits_until_the_primer_volume_is_detached(self):
        held = [('csi-a', 'pvc-123'), ('csi-other', 'pvc-999')]
        value, calls = self.run_wait([held, held, [('csi-other', 'pvc-999')]])
        self.assertEqual(value['attachedAtCreate'], [])
        self.assertEqual(value['waitedSeconds'], 4)
        self.assertEqual(calls.count(['get', 'volumeattachments']), 3)

    def test_wait_is_bounded_and_recorded(self):
        held = [('csi-a', 'pvc-123')]
        value, _ = self.run_wait([held] * 100, seconds=10)
        self.assertEqual((value['attachedAtCreate'], value['waitedSeconds']), (['csi-a'], 10))


class ReaderHeld(unittest.TestCase):
    """Fault 2: the reader is bound to the primer Pod's node before the primer exits, so the RWO
    volume is never detached and re-attached between them."""
    job = {'metadata': {'name': 'primer'}, 'spec': {'activeDeadlineSeconds': 600, 'template': {
        'metadata': {'labels': {'nightscout.org/run-id': 'r'}},
        'spec': {'containers': [{'name': 'primer', 'image': 'app', 'imagePullPolicy': 'IfNotPresent',
                                 'securityContext': {}, 'resources': {}}],
                 'nodeSelector': {'kubernetes.io/hostname': 'n1'},
                 'volumes': [{'name': 'client-state', 'persistentVolumeClaim': {'claimName': 'fixture-primer-results'}}]}}}}
    inventory = {'namespace': 'ns', 'results': {'primer': {'claim': 'fixture-primer-results', 'file': 'tenants.json'}}}

    def test_reader_is_created_on_the_scheduled_primer_node(self):
        clock, calls, polls = Clock(), [], iter([[], [{'spec': {}}], [{'spec': {'nodeName': 'n1'}}]])
        def run(args, input=None, **kwargs):
            calls.append(args[:2])
            if args[:2] == ['get', 'pods']:
                return subprocess.CompletedProcess(args, 0, json.dumps({'items': next(polls)}).encode())
            body = json.loads(input)
            calls.append(body)
            return subprocess.CompletedProcess(args, 0, json.dumps({'metadata': {'name': 'fixture-reader-x', 'uid': 'u'}}).encode())
        held = reader.hold_reader(run, self.job, self.inventory, clock.now + 3600, clock)
        pod = calls[-1]
        self.assertEqual((held['name'], held['node']), ('fixture-reader-x', 'n1'))
        self.assertEqual(pod['spec']['nodeName'], 'n1')
        self.assertEqual(pod['spec']['volumes'], [{'name': 'client-state', 'persistentVolumeClaim':
                         {'claimName': 'fixture-primer-results', 'readOnly': True}}])
        self.assertNotIn(['get', 'volumeattachments'], calls)
        with self.assertRaisesRegex(RuntimeError, 'PRIMER_UNSCHEDULED'):
            reader.hold_reader(lambda args, **kw: subprocess.CompletedProcess(args, 0, b'{"items": []}'),
                               self.job, self.inventory, clock.now + 5, clock)

    def test_a_held_reader_is_read_without_a_new_pod_or_attachment_wait(self):
        calls = []
        def fake(argv, **kwargs):
            args = argv[3:]
            calls.append(args[:2])
            if args[:2] == ['get', 'pod']:
                body = {'metadata': {'uid': 'u'}, 'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}
            elif args[0] == 'exec':
                body = {'version': 1, 'tenants': []}
            else:
                body = {'items': []}
            return subprocess.CompletedProcess(argv, 0, json.dumps(body).encode())
        directory = Path(tempfile.mkdtemp())/'fixture'
        inventory = {**self.inventory, 'storage': {'claims': {}}}
        with patch.object(reader.subprocess, 'run', side_effect=fake), \
             patch('contract.tenant_projection', return_value=[]):
            reader.read_roster(['kubectl', '-n', 'ns'], self.job, inventory, directory, 0, 1e12, 'claim',
                               {'name': 'fixture-reader-x', 'uid': 'u', 'node': 'n1'})
        self.assertNotIn(['create', '-f'], calls)
        self.assertNotIn(['get', 'volumeattachments'], calls)
        self.assertTrue((directory/'reader-held.json').is_file())


if __name__ == '__main__':
    unittest.main()
