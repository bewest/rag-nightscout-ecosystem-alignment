"""Evaluator K>1 (binding slices.evaluator): census, progress per ordinal, readiness, seed K and
fixture K, and the reader's detach wait. Synthetic replies only; no cluster."""
import copy
import json
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
        rendered[-1]['spec']['replicas'] = 9
        with self.assertRaisesRegex(k.Refused, 'EVALUATOR_SLICES_UNSUPPORTED'):
            k.validate(c, inv, rendered)
        rendered[-1]['spec']['replicas'] = 2
        rendered[2]['spec']['replicas'] = 2
        with self.assertRaisesRegex(k.Refused, 'WORKLOAD_REPLICA_CENSUS_UNSUPPORTED:StatefulSet/postgres'):
            k.validate(c, inv, rendered)

    def test_k1_census_unchanged(self):
        c, inv, rendered, client = sliced(1)
        observed = k.observe(c, k.validate(c, inv, rendered), client)
        self.assertEqual(k.selected_pod(c, observed, 'evaluator'), ('evaluator-0', 'evaluator'))
        self.assertEqual(k.evaluator_services(1), ['evaluator'])

    def test_readiness_waits_for_every_replica(self):
        one, two = ('uid-0', (('evaluator', 0),)), ('uid-1', (('evaluator', 0),))
        self.assertIsNone(producer_startup.replica_identity([one], 2))
        self.assertEqual(producer_startup.replica_identity([two, one], 2), (one, two))


def static_page(ordinal, count, runtime):
    rows = []
    for index, tenant in enumerate((A, B)):
        mine = index % count == ordinal
        rows.append({'tenant': tenant, 'admitted': mine, 'ready': mine, 'code': None, 'evaluation': {'alert': None},
                     'cycles': 1, 'progress': {'generation': 1, 'completedAcquisitions': 1, 'completedTimeCycles': 0,
                                               'failedCompletions': 0, 'lastCompletedAgeMs': 1},
                     'jobs': dict.fromkeys(k.evaluator_progress.JOB_FLAGS, False), 'dueAt': None, 'dueReason': None})
    configured = {'ordinal': ordinal, 'mode': 'static', 'count': count, 'rule': 'sha256-modulo-v1', 'leaseMs': None}
    return {'selected': [A, B], 'selfOrdinal': ordinal, 'selfMode': 'static', 'selfCount': count,
            'view': {'kind': 'evaluator', 'runtimeId': runtime, 'configured': configured, 'observed': None,
                     'gate': {'eligible': True, 'reason': None, 'members': count}, 'tenants': rows}}


class Progress(unittest.TestCase):
    def test_each_ordinal_is_read_in_its_own_pod_and_retained_separately(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        d = Path(tmp.name); out = d/'load'; out.mkdir()
        c, inv, rendered, client = sliced(2)
        clock = Clock()
        c.update(tenants=2, tier='discovery')
        c['deadlines'] = {'workUntil': iso(clock.now+7200), 'cleanupUntil': iso(clock.now+7800)}
        objects = k.validate(c, inv, rendered)
        baseline = k.observe(c, objects, client)
        pages = {'evaluator-0': static_page(0, 2, R), 'evaluator-1': static_page(1, 2, S)}
        targets = []
        def call(args, **kwargs):
            targets.append(args[2])
            return json.dumps(pages[args[2]]).encode()+b'\n'
        client.call = Mock(side_effect=call)
        roster = [{'id': t, 'token': 'synthetic', 'host': 'synthetic.test'} for t in (A, B)]
        with patch.object(k.time, 'time', clock.time), patch.object(k, 'active_baseline', return_value=baseline), \
             patch.object(execute, 'roster', return_value=roster):
            value = execute.retained_progress(d, out, c, objects, client, 'progress-before')
        self.assertIsNotNone(value, (out/'progress-before-failure.json').read_text() if (out/'progress-before-failure.json').exists() else '')
        self.assertEqual(sorted(targets), ['evaluator-0', 'evaluator-1'])
        self.assertEqual({s: v['ordinal'] for s, v in value['instances'].items()}, {'evaluator': 0, 'evaluator-2': 1})
        self.assertEqual({t: v['service'] for t, v in value['owners'].items()}, {A: 'evaluator', B: 'evaluator-2'})
        first = k.document(out/'progress-before-response.json')
        second = k.document(out/'progress-before-evaluator-2-response.json')
        self.assertEqual((first['podUid'], second['podUid']), ('uid-evaluator-0', 'uid-evaluator-1'))
        self.assertTrue((out/'progress-before.private.jsonl').is_file() and (out/'progress-before-evaluator-2.private.jsonl').is_file())


class SeedAndFixtureK(unittest.TestCase):
    def test_seed_environment_follows_the_binding(self):
        self.assertEqual(fixture_copy.seed_environment({}), {})
        k2 = {'slices': {'evaluator': 2}, 'seed': {'environment': {'NS_EVALUATOR_WORKERS': '2'}}}
        self.assertEqual(fixture_copy.seed_environment(k2), {'NS_EVALUATOR_WORKERS': '2'})
        with self.assertRaisesRegex(fixture_copy.Refused, 'SEED_EVALUATOR_SLICES'):
            fixture_copy.seed_environment({'slices': {'evaluator': 2}})
        self.assertEqual(fixture_copy.slices_record({}), {})
        self.assertEqual(fixture_copy.slices_record(k2), {'evaluatorSlices': 2})

    def test_restore_refuses_a_fixture_seeded_for_another_k(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)/'fixture'; directory.mkdir(mode=0o700)
        parts = fixture_copy.PARTS
        manifest = {'version': 1, 'handles': dict.fromkeys(parts, 'h'), 'sizes': dict.fromkeys(parts, '1Gi'),
                    'driver': 'dobs.csi.digitalocean.com', 'tenants': 1000, 'postgresImage': 'pg',
                    'snapshotClass': 's', 'storageClass': 'c'}
        for name, value in ((fixture_copy.MANIFEST, manifest), (fixture_copy.SECRETS, [])):
            (directory/name).write_text(json.dumps(value)); (directory/name).chmod(0o600)
        chosen = {'mode': 'restore', 'directory': str(directory)}
        never = '/nonexistent/jsonnet'  # the refusal precedes any render
        with self.assertRaisesRegex(fixture_copy.Refused, 'EVALUATOR_SLICES_CHANGED'):
            fixture_copy.render(never, '/nonexistent', 'ns', 'run', chosen, 1000, 'pg', 2)
        manifest['evaluatorSlices'] = 2
        (directory/fixture_copy.MANIFEST).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(fixture_copy.Refused, 'EVALUATOR_SLICES_CHANGED'):
            fixture_copy.render(never, '/nonexistent', 'ns', 'run', chosen, 1000, 'pg', 1)
        with self.assertRaises(FileNotFoundError):  # K matches: proceeds to the renderer
            fixture_copy.render(never, '/nonexistent', 'ns', 'run', chosen, 1000, 'pg', 2)


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


if __name__ == '__main__':
    unittest.main()
