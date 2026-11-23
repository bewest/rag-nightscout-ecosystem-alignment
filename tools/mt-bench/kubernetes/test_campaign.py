"""Cluster-resident campaigns: seal verification, collect-before-delete, controller resume, census, close, the in-cluster
fixture catalog, and offline rescore of a fetched packet. Fakes stand in for the store and kubectl; the live S3 controls
run when EVIDENCE_STORE_TEST_ENDPOINT is set (a local S3-compatible store), the kind controls in test_campaign_kind.py."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import campaign
import evidence_store
import packet_seal


class FakeStore:
    def __init__(self, bucket='lane9-test'):
        self.bucket, self.objects, self.exists, self.deleted = bucket, {}, True, []

    def put(self, key, body, content_type=None):
        self.objects[key] = bytes(body)

    def get(self, key):
        if key not in self.objects:
            raise evidence_store.StoreError(404, 'NoSuchKey')
        return self.objects[key]

    def delete(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)

    def list(self, prefix=''):
        return [{'key': k, 'bytes': len(v), 'etag': ''} for k, v in sorted(self.objects.items()) if k.startswith(prefix)]

    def bucket_exists(self):
        return self.exists

    def create_bucket(self):
        self.exists = True

    def delete_bucket(self):
        assert not self.objects
        self.exists = False

    def describe(self):
        return {'bucket': self.bucket}


def manifest(**extra):
    m = {'version': 1, 'campaign': 'c1', 'runner': 'synthetic', 'controllerImage': 'kind.local/controller:test',
         'caseDeadlineSeconds': 600, 'maxAttempts': 2, 'synthetic': {'image': 'kind.local/controller:test'},
         'store': {'endpoint': 'http://s3.local:9000', 'bucket': 'lane9-test', 'addressing': 'path'},
         'cases': [{'name': 'one'}, {'name': 'two'}]}
    m.update(extra)
    return m


class FakeKube:
    """Namespaces, supervisor Jobs and cleanup ConfigMaps; a supervisor 'runs' when its case is released or its
    heartbeat is stale, by writing its result ConfigMap."""

    def __init__(self):
        self.namespaces, self.jobs, self.configmaps, self.calls = {}, set(), {}, []
        self.cluster = {k: [] for k in ('pvc', 'pv', 'services', 'volumesnapshotcontents', 'clusterroles')}

    def __call__(self, argv, data=None, check=True):
        self.calls.append(list(argv))
        a = [x for x in argv if not x.startswith('--')]
        if a[:1] == ['-n']:
            ns, a = a[1], a[2:]
        else:
            ns = None
        if a[:2] == ['get', 'namespace']:
            got = self.namespaces.get(a[2])
            if 'name' in argv:
                return 'namespace/' + a[2] if got else ''
            if any(x.startswith('jsonpath=') for x in argv):
                return got['labels'].get('nightscout.org/run-id', '') if got else ''
            return json.dumps({'metadata': {'name': a[2], 'labels': got['labels'], 'annotations': got['annotations']}}) if got else ''
        if a[:2] == ['get', 'namespaces']:
            return json.dumps({'items': [{'metadata': {'name': n, 'labels': v['labels']}} for n, v in self.namespaces.items()]})
        if a[0] == 'get' and a[1] in ('pvc', 'pv', 'services', 'volumesnapshotcontents', 'clusterroles', 'clusterrolebindings',
                                      'validatingadmissionpolicies', 'validatingadmissionpolicybindings', 'jobs', 'pods',
                                      'configmaps', 'secrets', 'serviceaccounts', 'roles', 'rolebindings'):
            return json.dumps({'items': self.cluster.get(a[1], [])})
        if a[:2] == ['get', 'job']:
            return json.dumps({'metadata': {'name': a[2]}}) if a[2] in self.jobs else ''
        if a[:2] == ['get', 'configmap']:
            got = self.configmaps.get(a[2])
            return json.dumps({'data': {'result': got}}) if got else ''
        if a[0] == 'annotate':
            if a[2] not in self.namespaces:
                raise subprocess.CalledProcessError(1, argv)
            key, value = a[3].split('=', 1)
            self.namespaces[a[2]]['annotations'][key] = value
            if key == 'nightscout.org/case-released':
                self.finish(a[2], 'released')
            return ''
        if a[0] == 'apply':
            doc = json.loads(data)
            for item in doc.get('items', [doc]):
                if item['kind'] == 'Namespace':
                    self.namespaces[item['metadata']['name']] = {'labels': item['metadata']['labels'], 'annotations': {}}
                if item['kind'] == 'Job':
                    self.jobs.add(item['metadata']['name'])
            return ''
        if a[:2] == ['delete', 'namespace']:
            self.namespaces.pop(a[2], None)
            return ''
        if a[0] == 'delete':
            if a[1] == 'job':
                self.jobs.discard(a[2])
            if a[1] == 'configmap':
                self.configmaps.pop(a[2], None)
            return ''
        return ''

    def finish(self, ns, reason):
        rid = self.namespaces[ns]['labels']['nightscout.org/run-id']
        if 'case-supervisor-' + rid in self.jobs:
            self.namespaces.pop(ns)
            self.configmaps['case-cleanup-' + rid] = json.dumps({'verdict': 'CLEANED', 'reason': reason, 'runId': rid})


class Runner:
    calls = []
    outcome = {'state': 'scored', 'verdict': 'PASS'}

    def __init__(self, m, call):
        self.call = call

    def namespace(self, rid):
        return 'ns-' + rid

    def cluster_scoped(self, rid):
        return ()

    def run(self, case, rid, ns, directory, deadline):
        Runner.calls.append(rid)
        self.call(['apply', '-f', '-'], json.dumps({'kind': 'Namespace', 'metadata': {'name': ns, 'labels': {'nightscout.org/run-id': rid}}}))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'k6-summary.json').write_text('{"metrics": {}}')
        (directory.parent / (rid + '.inputs')).mkdir(exist_ok=True)
        (directory.parent / (rid + '.inputs/profile.json')).write_text('{}')   # the existing path's sibling directory
        import time
        time.sleep(0.3)   # long enough for the watcher to see the namespace and apply the supervisor
        if isinstance(Runner.outcome, Exception):
            raise Runner.outcome
        return dict(Runner.outcome)

    validate = staticmethod(lambda m: None)


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        campaign.RUNNERS['fake'] = Runner
        self.addCleanup(campaign.RUNNERS.pop, 'fake')
        Runner.calls, Runner.outcome = [], {'state': 'scored', 'verdict': 'PASS'}
        self.store, self.kube = FakeStore(), FakeKube()

    def controller(self, m=None):
        return campaign.Controller(m or manifest(runner='fake'), self.store, self.kube, workdir=self.tmp / 'work',
                                   sleep=lambda s: None, heartbeat_seconds=0.05, sync_seconds=0, supervisor_wait=5, pod='pod-1')


class Manifest(unittest.TestCase):
    def test_refusals(self):
        campaign.validate(manifest())
        for bad, code in [(dict(campaign='Bad_Name'), 'NAME'), (dict(runner='other'), 'RUNNER'),
                          (dict(controllerImage='registry/x:latest'), 'CONTROLLER_IMAGE_DIGEST'),
                          (dict(cases=[{'name': 'a'}, {'name': 'a'}]), 'CASE_DUPLICATE'),
                          (dict(store={'endpoint': 'x', 'bucket': 'b', 'secretKey': 's'}), 'STORE_CREDENTIALS_IN_MANIFEST')]:
            with self.assertRaisesRegex(campaign.Refused, code):
                campaign.validate(manifest(**bad))

    def test_render_confines_writes_and_carries_no_credentials(self):
        items = campaign.render(manifest())['items']
        kinds = [i['kind'] for i in items]
        self.assertEqual(kinds[-1], 'Job')   # applied after the policy
        policy = next(i for i in items if i['kind'] == 'ValidatingAdmissionPolicy')
        self.assertIn("startsWith('c1-')", policy['spec']['validations'][0]['expression'])
        self.assertIn('system:serviceaccount:bench-control:campaign-c1', policy['spec']['matchConditions'][0]['expression'])
        job = items[-1]
        self.assertEqual(job['spec']['podReplacementPolicy'], 'Failed')
        env = job['spec']['template']['spec']['containers'][0]['env']
        self.assertTrue(all('value' not in e for e in env if 'KEY' in e['name']))
        self.assertNotIn('Secret', kinds)


class Seal(Base):
    def packet(self):
        d = self.tmp / 'case'
        (d / 'load').mkdir(parents=True)
        (d / 'load/k6.log').write_text('a\n')
        (d / 'load/window.json').write_text('{}')
        (d / 'runtime').mkdir()
        (d / 'runtime/data-roster.private.json').write_text('[]')   # private: never uploaded
        return d

    def test_verify_and_its_three_failure_controls(self):
        d = self.packet()
        up = packet_seal.Uploader(self.store, 'c1/cases/x/attempt-1')
        seal = up.seal(d, 'scored')
        self.assertEqual(sorted(seal['files']), ['load/k6.log', 'load/window.json'])
        self.assertNotIn('c1/cases/x/attempt-1/files/runtime/data-roster.private.json', self.store.objects)
        self.assertTrue(packet_seal.verify(d, seal)['verified'])
        (d / 'load/k6.log').write_text('b\n')
        with self.assertRaisesRegex(packet_seal.SealError, 'ALTERED'):
            packet_seal.verify(d, seal)
        (d / 'load/k6.log').unlink()
        with self.assertRaisesRegex(packet_seal.SealError, 'MISSING'):
            packet_seal.verify(d, seal)
        (d / 'load/k6.log').write_text('a\n')
        (d / 'load/extra').write_text('x')
        with self.assertRaisesRegex(packet_seal.SealError, 'UNSEALED'):
            packet_seal.verify(d, seal)

    def test_progressive_upload_sends_only_new_or_changed_files(self):
        d = self.packet()
        up = packet_seal.Uploader(self.store, 'p')
        self.assertEqual(up.sync(d), 2)
        self.assertEqual(up.sync(d), 0)
        (d / 'load/k6.log').write_text('a\nb\n')
        self.assertEqual(up.sync(d), 1)


class Collect(Base):
    def finished(self, case='one', state='scored', tamper=False, extra=False):
        d = self.tmp / ('p-' + case)
        d.mkdir()
        (d / 'result.json').write_text('{"verdict": "PASS"}')
        pfx = campaign.attempt_prefix('c1', case, 1)
        packet_seal.Uploader(self.store, pfx).seal(d, state)
        if tamper:
            self.store.objects[pfx + 'files/result.json'] = b'{"verdict": "FAIL"}'
        if extra:
            self.store.objects[pfx + 'files/late.json'] = b'{}'
        self.store.put(campaign.case_prefix('c1', case) + 'status.json',
                       json.dumps({'case': case, 'state': state, 'attempts': [{'attempt': 1}]}).encode())

    def test_collect_verifies_then_deletes_and_the_bucket_reads_empty(self):
        self.store.put('c1/campaign.json', b'{}')
        self.finished('one')
        self.finished('two', state='UNMEASURED')
        report = campaign.collect(self.store, 'c1', self.tmp / 'out')
        self.assertEqual(report['collected'], {'one': 'scored', 'two': 'UNMEASURED'})
        self.assertEqual(self.store.objects, {})
        self.assertEqual(json.loads((self.tmp / 'out/one/attempt-1/files/result.json').read_text())['verdict'], 'PASS')
        self.assertTrue((self.tmp / 'out/campaign.json').is_file())

    def test_an_altered_object_fails_verification_and_nothing_of_it_is_deleted(self):
        self.finished('one', tamper=True)
        before = dict(self.store.objects)
        report = campaign.collect(self.store, 'c1', self.tmp / 'out')
        self.assertEqual(report['failures']['one'][0]['code'], 'PACKET_FILE_ALTERED')
        self.assertEqual(self.store.objects, before)
        self.assertEqual(self.store.deleted, [])
        self.assertFalse((self.tmp / 'out/one/attempt-1').exists())

    def test_a_missing_object_fails_verification(self):
        self.finished('one')
        del self.store.objects[campaign.attempt_prefix('c1', 'one', 1) + 'files/result.json']
        report = campaign.collect(self.store, 'c1', self.tmp / 'out')
        self.assertEqual(report['failures']['one'][0]['code'], 'PACKET_FILE_MISSING')
        self.assertEqual(self.store.deleted, [])

    def test_an_unsealed_object_is_never_deleted(self):
        self.finished('one', extra=True)
        report = campaign.collect(self.store, 'c1', self.tmp / 'out')
        self.assertEqual(report['kept'], [campaign.attempt_prefix('c1', 'one', 1) + 'files/late.json'])
        self.assertIn(campaign.case_prefix('c1', 'one') + 'status.json', self.store.objects)

    def test_a_running_case_is_pending_and_one_case_can_be_fetched_on_demand(self):
        self.store.put('c1/campaign.json', b'{}')
        self.finished('one')
        self.store.put(campaign.case_prefix('c1', 'two') + 'status.json', b'{"state": "running", "attempts": []}')
        report = campaign.collect(self.store, 'c1', self.tmp / 'out', case='one')
        self.assertEqual((report['collected'], report['pending']), ({'one': 'scored'}, []))
        self.assertIn('c1/campaign.json', self.store.objects)
        self.assertEqual(campaign.collect(self.store, 'c1', self.tmp / 'out')['pending'], ['two'])


class ControllerRuns(Base):
    def test_cases_run_in_order_sealed_and_cleaned_by_their_supervisor(self):
        done = self.controller().run()
        self.assertEqual({k: v['state'] for k, v in done.items()}, {'one': 'scored', 'two': 'scored'})
        self.assertEqual(Runner.calls, ['c1-one-a1', 'c1-two-a1'])
        for case in ('one', 'two'):
            seal = json.loads(self.store.objects[campaign.attempt_prefix('c1', case, 1) + 'SEAL.json'])
            self.assertIn('k6-summary.json', seal['files'])
            self.assertIn('campaign-siblings/c1-%s-a1.inputs/profile.json' % case, seal['files'])
            cleanup = json.loads(self.store.objects[campaign.attempt_prefix('c1', case, 1) + 'files/campaign-cleanup.json'])
            self.assertEqual((cleanup['verdict'], cleanup['by'], cleanup['reason']), ('CLEANED', 'supervisor', 'released'))
        self.assertEqual(self.kube.namespaces, {})
        self.assertEqual(self.kube.jobs, set())   # supervisors retired after their result is read

    def test_a_restarted_controller_skips_finished_cases_and_reruns_the_interrupted_one_fresh(self):
        self.controller(manifest(runner='fake', cases=[{'name': 'one'}])).run()
        # Attempt 1 of case two was running when its controller Pod died: its namespace, its supervisor, one uploaded file.
        self.kube.namespaces['ns-c1-two-a1'] = {'labels': {'nightscout.org/run-id': 'c1-two-a1'}, 'annotations': {}}
        self.kube.jobs.add('case-supervisor-c1-two-a1')
        self.kube.configmaps['case-cleanup-c1-two-a1'] = json.dumps({'verdict': 'CLEANED', 'reason': 'heartbeat-stale'})
        pfx = campaign.attempt_prefix('c1', 'two', 1)
        self.store.put(pfx + 'files/k6.log', b'partial\n')
        self.store.put(campaign.case_prefix('c1', 'two') + 'status.json', json.dumps(
            {'case': 'two', 'state': 'running', 'attempts': [{'attempt': 1, 'runId': 'c1-two-a1', 'namespace': 'ns-c1-two-a1',
                                                             'state': 'running', 'controllerPod': 'pod-0'}]}).encode())
        Runner.calls = []
        done = self.controller().run()
        self.assertEqual(Runner.calls, ['c1-two-a2'])   # one is not rerun; two runs again in a fresh namespace
        two = done['two']
        self.assertEqual(two['state'], 'scored')
        self.assertEqual([(a['attempt'], a['state'], a.get('reason')) for a in two['attempts']],
                         [(1, 'UNMEASURED', 'controller-interrupted'), (2, 'scored', None)])
        seal = json.loads(self.store.objects[pfx + 'SEAL.json'])
        self.assertEqual(sorted(seal['files']), ['controller-interrupted.json', 'k6.log'])
        note = json.loads(self.store.objects[pfx + 'files/controller-interrupted.json'])
        self.assertEqual((note['cleanup']['reason'], note['interruptedPod']), ('heartbeat-stale', 'pod-0'))
        report = campaign.collect(self.store, 'c1', self.tmp / 'out')   # the interrupted attempt's seal verifies
        self.assertEqual(report['failures'], {})

    def test_interrupted_before_a_supervisor_existed_the_controller_cleans_up_itself(self):
        self.kube.namespaces['ns-c1-one-a1'] = {'labels': {'nightscout.org/run-id': 'c1-one-a1'}, 'annotations': {}}
        self.store.put(campaign.case_prefix('c1', 'one') + 'status.json', json.dumps(
            {'case': 'one', 'state': 'running', 'attempts': [{'attempt': 1, 'runId': 'c1-one-a1', 'namespace': 'ns-c1-one-a1'}]}).encode())
        done = self.controller(manifest(runner='fake', cases=[{'name': 'one'}])).run()
        self.assertNotIn('ns-c1-one-a1', self.kube.namespaces)
        self.assertEqual(done['one']['attempts'][0]['cleanup'], 'CLEANED')

    def test_attempts_are_bounded(self):
        self.store.put(campaign.case_prefix('c1', 'one') + 'status.json', json.dumps(
            {'case': 'one', 'state': 'running', 'attempts': [
                {'attempt': 1, 'runId': 'c1-one-a1', 'namespace': 'ns-c1-one-a1', 'state': 'UNMEASURED'},
                {'attempt': 2, 'runId': 'c1-one-a2', 'namespace': 'ns-c1-one-a2'}]}).encode())
        done = self.controller(manifest(runner='fake', cases=[{'name': 'one'}])).run()
        self.assertEqual(done['one']['state'], 'UNMEASURED')
        self.assertEqual(Runner.calls, [])

    def test_a_runner_crash_is_failed_never_scored_and_still_sealed(self):
        Runner.outcome = RuntimeError('boom')
        done = self.controller(manifest(runner='fake', cases=[{'name': 'one'}])).run()
        self.assertEqual((done['one']['state'], done['one']['reason']), ('failed', 'RuntimeError'))
        self.assertIn(campaign.attempt_prefix('c1', 'one', 1) + 'SEAL.json', self.store.objects)

    def test_unconfirmed_cleanup_never_scores(self):
        self.kube.finish = lambda ns, reason: None   # the supervisor never reports
        done = self.controller(manifest(runner='fake', cases=[{'name': 'one'}])).run()
        self.assertEqual(done['one']['state'], 'UNMEASURED')
        self.assertEqual(done['one']['attempts'][0]['cleanup'], 'UNCONFIRMED')


class CensusClose(Base):
    def test_census_is_non_empty_while_anything_remains_and_close_needs_an_empty_bucket(self):
        m = manifest()
        self.assertTrue(campaign.census(m, self.store, self.kube)['empty'] is False)   # the bucket itself bills
        self.store.put('c1/x', b'1')
        self.kube.namespaces['ns-c1-one-a1'] = {'labels': {'nightscout.org/run-id': 'c1-one-a1'}, 'annotations': {}}
        self.kube.namespaces['ns-other'] = {'labels': {'nightscout.org/run-id': 'c2-one-a1'}, 'annotations': {}}
        self.kube.cluster['pv'] = [{'metadata': {'name': 'pvc-1'}, 'spec': {'claimRef': {'namespace': 'ns-c1-one-a1'}}}]
        self.kube.cluster['services'] = [{'metadata': {'namespace': 'ns-c1-one-a1', 'name': 'edge'}, 'spec': {'type': 'LoadBalancer'}}]
        self.kube.cluster['volumesnapshotcontents'] = [
            {'metadata': {'name': 'run-snap', 'labels': {'nightscout.org/run-id': 'c1-one-a1'}}},
            {'metadata': {'name': 'seed-snap', 'labels': {'nightscout.org/run-id': 'c1-one-a1', 'nightscout.org/fixture': 'c1-seed'}}}]
        got = campaign.census(m, self.store, self.kube)
        self.assertEqual(got['billable']['namespaces'], ['ns-c1-one-a1'])
        self.assertEqual(got['billable']['persistentVolumes'], ['pvc-1'])
        self.assertEqual(got['billable']['loadBalancers'], ['ns-c1-one-a1/edge'])
        self.assertEqual(got['billable']['volumeSnapshotContents'], ['run-snap'])
        self.assertEqual(got['retainedByFixture'], ['seed-snap'])
        with self.assertRaisesRegex(campaign.Refused, 'BUCKET_NOT_EMPTY'):
            campaign.close(m, self.store, self.kube)
        self.assertTrue(self.store.exists)
        del self.store.objects['c1/x']
        self.kube.namespaces.pop('ns-c1-one-a1')
        self.kube.cluster.update(pv=[], services=[], volumesnapshotcontents=[])
        got = campaign.close(m, self.store, self.kube)
        self.assertEqual((got['empty'], self.store.exists), (True, False))

    def test_doctl_rows_are_read_only_lists(self):
        seen = []

        def doctl(argv):
            seen.append(argv)
            return json.dumps({'node-pool': [{'name': 'bench-1k'}, {'name': 'default'}],
                               'volume': [{'name': 'pvc-9', 'droplet_ids': []}, {'name': 'pvc-8', 'droplet_ids': [1]}],
                               'load-balancer': []}[argv[1] if argv[0] == 'compute' else 'node-pool'])
        self.store.exists = False
        got = campaign.census(manifest(nodePools=['bench-1k']), self.store, self.kube, doctl, 'bench')
        self.assertEqual(got['billable'], {'nodePools': ['bench-1k'], 'unattachedVolumes': ['pvc-9']})
        self.assertTrue(all(a[-3] == 'list' or a[2] == 'list' or 'list' in a for a in seen))


class Catalog(Base):
    def test_a_workstation_fixture_restores_from_bench_control_objects(self):
        import fixture_catalog
        import fixture_copy
        key = fixture_catalog.key(tenants=1000, image='sha256:' + 'a' * 64, postgres_image='sha256:' + 'b' * 64,
                                  schema='migrations-tree:abc', transport='writer-driven')
        catalog = fixture_catalog.Catalog(self.tmp / 'ws/catalog.json')
        directory = catalog.reserve(key, 'kubernetes')
        directory.mkdir(mode=0o700)
        parts = fixture_copy.PARTS
        (directory / fixture_copy.MANIFEST).write_text(json.dumps({'version': 1, 'fixtureId': 'seed-run', 'driver': 'dobs.csi',
            'handles': dict.fromkeys(parts, 'h'), 'sizes': dict.fromkeys(parts, '1Gi'), 'seedContents': dict.fromkeys(parts, 'c'),
            'storageClass': 's', 'snapshotClass': 'v'}))
        (directory / fixture_copy.SECRETS).write_text(json.dumps([{'name': 'ns-ca', 'type': 'Opaque', 'data': {'k': 'dg=='}}]))
        for f in (fixture_copy.MANIFEST, fixture_copy.SECRETS):
            (directory / f).chmod(0o600)
        catalog.register(key, 'kubernetes', {'fixtureId': 'seed-run', 'volumeSnapshotContents': {}, 'providerSnapshots': {}, 'seedCase': 'x'})
        applied = []
        campaign.catalog_import(fixture_catalog.digest(key), self.tmp / 'ws/catalog.json',
                                lambda argv, data=None: applied.append(json.loads(data)) or '')
        cm, secret = applied
        self.assertNotIn('dg==', json.dumps(cm))   # credentials only in the Secret
        self.assertNotIn('directory', cm['data']['record.json'])

        def call(argv, data=None):
            if 'configmap' in argv:
                return json.dumps({'items': [cm]})
            return json.dumps(secret)
        path = campaign.sync_catalog(call, self.tmp / 'pod/catalog')
        hit = fixture_catalog.Catalog(path).lookup(key, 'kubernetes')
        self.assertEqual(hit['status'], 'ready')
        self.assertEqual(fixture_copy.selection('restore', hit['directory'])['storageClass'], 's')
        self.assertEqual(json.loads((Path(hit['directory']) / fixture_copy.SECRETS).read_text())[0]['name'], 'ns-ca')
        cm['data']['key.json'] = json.dumps(dict(key, tenants=2000))   # control: a key that does not match its name
        with self.assertRaisesRegex(campaign.Refused, 'DIGEST_MISMATCH'):
            campaign.sync_catalog(call, self.tmp / 'pod/catalog')


class Rescore(Base):
    def test_a_fetched_packet_rescores_offline_like_the_original(self):
        import capacity_results
        from test_capacity_results import CapacityPublication
        source = CapacityPublication('test_roundtrip_after_source_removal_and_corruption_control')
        source.setUp()
        self.addCleanup(source.doCleanups)
        case = source.load.parent.parent / 'case'
        root = case / 'runtime/packet/experiment/capacity-results'
        capacity_results.publish(source.load, root)
        expected = capacity_results.rescore(root)
        pfx = campaign.attempt_prefix('c1', 'one', 1)
        packet_seal.Uploader(self.store, pfx).seal(case, 'scored')
        self.store.put(campaign.case_prefix('c1', 'one') + 'status.json', b'{"state": "scored", "attempts": [{"attempt": 1}]}')
        campaign.collect(self.store, 'c1', self.tmp / 'out')
        got = campaign.rescore(self.tmp / 'out')
        self.assertEqual(list(got.values()), [expected])


@unittest.skipUnless(os.environ.get('EVIDENCE_STORE_TEST_ENDPOINT'), 'set EVIDENCE_STORE_TEST_ENDPOINT (+_ACCESS_KEY/_SECRET_KEY) to a local S3-compatible store')
class LiveStore(unittest.TestCase):
    def store(self, bucket, secret=None):
        e = os.environ
        return evidence_store.Store(e['EVIDENCE_STORE_TEST_ENDPOINT'], bucket, e['EVIDENCE_STORE_TEST_ACCESS_KEY'],
                                    secret or e['EVIDENCE_STORE_TEST_SECRET_KEY'], addressing='path')

    def test_objects_listing_pages_and_a_bad_signature(self):
        s = self.store('lane9-live-%d' % os.getpid())
        s.create_bucket()
        try:
            for i in range(1003):   # one more page than the 1,000-key default
                s.put('c/%04d' % i, b'x')
            self.assertEqual(len(s.list('c/')), 1003)
            s.put('c/a b+c.json', b'{"x": 1}')
            self.assertEqual(s.get('c/a b+c.json'), b'{"x": 1}')
            with self.assertRaises(evidence_store.StoreError) as bad:
                self.store(s.bucket, secret='wrong').list('c/')
            self.assertEqual(bad.exception.status, 403)
            with self.assertRaises(evidence_store.StoreError) as missing:
                s.get('c/absent')
            self.assertEqual(missing.exception.status, 404)
        finally:
            for o in s.list(''):
                s.delete(o['key'])
            s.delete_bucket()
        self.assertFalse(s.bucket_exists())


if __name__ == '__main__':
    unittest.main()
