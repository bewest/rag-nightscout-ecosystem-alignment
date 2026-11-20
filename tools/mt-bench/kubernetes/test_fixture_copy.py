"""Kubernetes CSI snapshot fixture reuse offline: rendered objects and a recorded seed, restore and delete."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import fixture_copy as fc
import run_cleanup as rc

NS, RID = 'ns-synth-seed-1', 'seed-1'
PG = 'r/pg@sha256:' + '2'*64
JSONNET = Path(os.environ.get('K8S_JSONNET', '/mnt/data/nightscout-workspace/artifacts/staging-k8s-environment-20261117/tools/jsonnet-0.21.0/jsonnet'))
BINDING = os.environ.get('K8S_FIXTURE_BINDING')


class Cluster:
    """Recorded kubectl replies for one seed namespace after its primer completed."""
    def __init__(self, pods=0, retain=True):
        self.calls, self.pods, self.retain, self.policy, self.contents = [], pods, retain, {}, set()
        self.secrets = [{'metadata': {'name': n}, 'type': 'Opaque', 'data': {'k': 'c3ludGhldGlj'}}
                        for n in ('ns-postgres-password', 'ns-ca', 'ns-vault-tls', 'ns-config-api', 'ns-credentials-vault',
                                  'registry-pull', 'default-token')]
    def __call__(self, args, body=None):
        self.calls.append((args, body))
        if args[:2] == ['get', 'pods']:
            self.pods = max(0, self.pods - 1)
            return ('pod/x\n' if self.pods else '').encode()
        if args[0] == 'create':
            return json.dumps({**body, 'metadata': {**body['metadata'], 'uid': 'u-' + body['metadata']['name']}}).encode()
        if args[:2] == ['get', 'volumesnapshot']:
            self.contents.add('content-' + args[2])
            return json.dumps({'status': {'readyToUse': True, 'boundVolumeSnapshotContentName': 'content-' + args[2],
                                          'restoreSize': '1Gi'}}).encode()
        if args[0] == 'patch':
            if self.retain:
                self.policy[args[2]] = json.loads(args[-1])['spec']['deletionPolicy']
            return b''
        if args[:2] == ['get', 'volumesnapshotcontent']:
            return json.dumps({'spec': {'deletionPolicy': self.policy.get(args[2], 'Delete'), 'driver': 'dobs.csi.digitalocean.com'},
                               'status': {'snapshotHandle': 'handle-' + args[2]}}).encode()
        if args[:2] == ['get', 'secrets']:
            return json.dumps({'items': self.secrets}).encode()
        if args[:2] == ['delete', fc.CONTENTS]:
            self.contents = {c for c in self.contents if self.policy.get(c) != 'Delete'}
        if args[:2] == ['get', fc.CONTENTS]:
            return ''.join(c + '\n' for c in self.contents).encode()
        return b''


class FixtureCopy(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def seeded(self, cluster=None):
        cluster = cluster or Cluster(pods=2)
        chosen = fc.selection('seed', self.root/'fixture-8', 'do-block-storage', 'do-block-storage')
        fc.quiesce(cluster, NS, RID, 1e12)
        snapshots = {'items': [{'kind': 'VolumeSnapshot', 'metadata': {'name': n, 'namespace': NS}} for n in fc.SNAPSHOTS.values()]}
        summary = fc.capture(cluster, NS, RID, chosen, snapshots,
                             {'tenants': 8, 'postgresImage': PG, 'coreCommit': 'a'*40, 'deployCommit': 'b'*40}, 1e12)
        return cluster, chosen, summary

    def test_seed_stops_writers_then_keeps_retained_handles_and_only_fixture_secrets(self):
        cluster, chosen, summary = self.seeded()
        verbs = [c[0][:2] for c in cluster.calls]
        self.assertEqual(verbs[0], ['scale', 'deployment,statefulset'])
        self.assertLess(verbs.index(['get', 'pods']), verbs.index(['create', '-f']))
        directory = Path(chosen['directory'])
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for name in (fc.MANIFEST, fc.SECRETS):
            self.assertEqual((directory/name).stat().st_mode & 0o777, 0o600)
        manifest = fc.read_manifest(directory)
        self.assertTrue(all(h.startswith('handle-content-') for h in manifest['handles'].values()))
        self.assertEqual((manifest['driver'], manifest['postgresImage'], manifest['coreCommit']),
                         ('dobs.csi.digitalocean.com', PG, 'a'*40))
        self.assertEqual(manifest['secrets'], sorted(['ns-postgres-password', 'ns-ca', 'ns-vault-tls',
                                                      'ns-config-api', 'ns-credentials-vault']))
        self.assertEqual(set(cluster.policy.values()), {'Retain'})
        self.assertTrue(all(fc.FIXTURE_LABEL in c[0][-1] for c in cluster.calls if c[0][0] == 'patch'))
        self.assertEqual(summary['tenants'], 8)

    def test_a_content_that_will_not_retain_refuses_before_writing_the_fixture(self):
        with self.assertRaisesRegex(fc.Refused, 'RETAIN'):
            self.seeded(Cluster(retain=False))
        self.assertFalse((self.root/'fixture-8').exists())

    def test_restore_creates_the_seed_secrets_and_refuses_another_population_or_postgres_image(self):
        _, chosen, _ = self.seeded()
        cluster = Cluster()
        self.assertEqual(len(fc.import_secrets(cluster, 'ns-synth-restore-1', 'restore-1', chosen['directory'])), 5)
        self.assertTrue(all(b['metadata']['labels'] == {fc.LABEL: 'restore-1'} for _, b in cluster.calls))
        manifest = fc.read_manifest(chosen['directory'])
        fc.check_restore(manifest, 8, PG)
        with self.assertRaisesRegex(fc.Refused, 'INPUT_TRANSPORT_CHANGED'):
            fc.check_restore(manifest, 8, PG, input_transport='writer-driven')
        record = fc.slices_record({'inputTransport':'writer-driven', 'slices':{'evaluator':2}})
        fc.check_restore({**manifest, **record}, 8, PG, 2, 'writer-driven')
        with self.assertRaisesRegex(fc.Refused, 'INPUT_TRANSPORT_CHANGED'):
            fc.check_restore({**manifest, **record}, 8, PG, 2)
        with self.assertRaisesRegex(fc.Refused, 'TENANTS_CHANGED'):
            fc.check_restore(manifest, 3000, PG)
        with self.assertRaisesRegex(fc.Refused, 'POSTGRES_IMAGE_CHANGED'):
            fc.check_restore(manifest, 8, 'r/pg@sha256:' + '3'*64)

    def test_deleting_the_fixture_sets_delete_policy_before_removing_its_contents(self):
        cluster, chosen, _ = self.seeded()
        result = fc.delete(cluster, chosen['directory'], 1e12)
        self.assertTrue(result['contentsAbsent'])
        self.assertEqual(set(cluster.policy.values()), {'Delete'})
        verbs = [c[0][:2] for c in cluster.calls]
        self.assertLess(max(i for i, v in enumerate(verbs) if v[0] == 'patch'), verbs.index(['delete', fc.CONTENTS]))

    def test_a_seed_directory_must_be_new_and_reuse_selects_existing_claims(self):
        (self.root/'taken').mkdir()
        with self.assertRaisesRegex(fc.Refused, 'SEED_DIRECTORY'):
            fc.selection('seed', self.root/'taken', 'do-block-storage', 'do-block-storage')
        self.assertEqual(fc.storage({'mode': 'disposable'}), {'mode': 'existing-claim', 'claims': fc.CLAIMS})

    def test_fixture_runs_delete_their_labelled_snapshot_contents(self):
        self.assertIn(fc.CONTENTS, rc.delete_commands(NS, RID, 120, rc.FIXTURE_SCOPED)[1][1])
        self.assertNotIn(fc.CONTENTS, rc.delete_commands(NS, RID, 120)[1][1])

    @unittest.skipUnless(BINDING and JSONNET.is_file(), 'needs K8S_FIXTURE_BINDING (deploy checkout) and jsonnet 0.21')
    def test_rendered_restore_binds_handles_in_the_fresh_namespace(self):
        _, chosen, _ = self.seeded()
        library = Path(BINDING)/'bindings/kubernetes/lib'
        seed = fc.render(str(JSONNET), library, NS, RID, chosen)['items']
        self.assertEqual(sorted(o['metadata']['name'] for o in seed), sorted(fc.CLAIMS.values()))
        self.assertTrue(all('dataSource' not in o['spec'] for o in seed))
        restore = fc.selection('restore', chosen['directory'])
        items = fc.render(str(JSONNET), library, 'ns-synth-restore-1', 'restore-1', restore, 8, PG)['items']
        self.assertEqual([o['kind'] for o in items], ['VolumeSnapshotContent', 'VolumeSnapshot']*4 + ['PersistentVolumeClaim']*4)
        for o in items:
            self.assertEqual(o['metadata']['labels'], {fc.LABEL: 'restore-1'})
            if o['kind'] == 'VolumeSnapshotContent':
                self.assertEqual(o['spec']['deletionPolicy'], 'Retain')
                self.assertTrue(o['spec']['source']['snapshotHandle'].startswith('handle-'))
                self.assertEqual(o['spec']['volumeSnapshotRef']['namespace'], 'ns-synth-restore-1')
            else:
                self.assertEqual(o['metadata']['namespace'], 'ns-synth-restore-1')
        claims = [o for o in items if o['kind'] == 'PersistentVolumeClaim']
        self.assertEqual({o['spec']['dataSource']['name'] for o in claims}, set(fc.SNAPSHOTS.values()))
        snaps = fc.snapshot_objects(str(JSONNET), library, NS, RID, chosen)['items']
        self.assertEqual({o['spec']['source']['persistentVolumeClaimName'] for o in snaps}, set(fc.CLAIMS.values()))
        with self.assertRaisesRegex(fc.Refused, 'TENANTS_CHANGED'):
            fc.render(str(JSONNET), library, 'ns-synth-restore-2', 'restore-2', restore, 9, PG)


if __name__ == '__main__':
    unittest.main()
