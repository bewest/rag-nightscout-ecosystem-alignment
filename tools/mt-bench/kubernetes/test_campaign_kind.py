"""Kind controls for cluster-resident campaigns (local kind cluster + a local S3-compatible store; never DigitalOcean).

  CAMPAIGN_KIND_CONTEXT=kind-lane9 CAMPAIGN_KIND_IMAGE=kind.local/lane9-controller:t1 \
  CAMPAIGN_STORE_CLUSTER=http://s3.lane9-store.svc:8333 CAMPAIGN_STORE_LOCAL=http://127.0.0.1:13901 \
  CAMPAIGN_STORE_ADMIN=KEY:SECRET CAMPAIGN_STORE_SCOPED=KEY:SECRET CAMPAIGN_STORE_SCOPED_BUCKET=lane9-scoped \
  python3 -B -m unittest test_campaign_kind

After `apply`, the workstation only reads (kubectl get, the status object) until it collects; a test that kills the
controller does so with one delete, as a reboot or a lost session would.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

import campaign
import evidence_store

E = os.environ
KIND = E.get('CAMPAIGN_KIND_CONTEXT', '')


def creds(name):
    return E[name].split(':', 1)


@unittest.skipUnless(KIND.startswith('kind-'), 'set CAMPAIGN_KIND_CONTEXT=kind-<name> and the store variables (module docstring)')
class Kind(unittest.TestCase):
    def k(self, *argv, check=True, stdin=None):
        return subprocess.run(['kubectl', '--context', KIND, *argv], capture_output=True, text=True, input=stdin,
                              check=check, timeout=180)

    def call(self, argv, data=None, check=True):
        q = self.k(*argv, check=check, stdin=data)
        return q.stdout

    def store(self, bucket, who='CAMPAIGN_STORE_ADMIN'):
        key, secret = creds(who)
        return evidence_store.Store(E['CAMPAIGN_STORE_LOCAL'], bucket, key, secret, addressing='path')

    def manifest(self, name, bucket, cases, **extra):
        m = {'version': 1, 'campaign': name, 'runner': 'synthetic', 'controllerImage': E['CAMPAIGN_KIND_IMAGE'],
             'caseDeadlineSeconds': 300, 'maxAttempts': 2, 'heartbeatGraceSeconds': 15, 'heartbeatSeconds': 3,
             'syncSeconds': 3, 'synthetic': {'image': E['CAMPAIGN_KIND_IMAGE']},
             'controllerResources': {'requests': {'cpu': '50m', 'memory': '64Mi'}},
             'store': {'endpoint': E['CAMPAIGN_STORE_CLUSTER'], 'bucket': bucket, 'addressing': 'path'}, 'cases': cases}
        m.update(extra)
        return campaign.validate(m)

    def apply(self, m, who='CAMPAIGN_STORE_ADMIN', create=True):
        key, secret = creds(who)
        env = dict(E, NS_EVIDENCE_ACCESS_KEY=key, NS_EVIDENCE_SECRET_KEY=secret)
        admin = self.store(m['store']['bucket'])
        if create and not admin.bucket_exists():
            admin.create_bucket()
        return campaign.apply(m, self.call, env=env, store=self.store(m['store']['bucket'], who))

    def wait(self, predicate, seconds, what):
        end = time.time() + seconds
        while time.time() < end:
            got = predicate()
            if got:
                return got
            time.sleep(2)
        self.fail('timed out waiting for ' + what)

    def job(self, m):
        out = self.k('-n', 'bench-control', 'get', 'job', 'campaign-' + m['campaign'], '-o', 'json', check=False).stdout
        return json.loads(out)['status'] if out else {}

    def statuses(self, m):
        return campaign.statuses(self.store(m['store']['bucket']), m['campaign'])

    def finish(self, m, out):
        store = self.store(m['store']['bucket'])
        report = campaign.collect(store, m['campaign'], out)
        self.assertEqual((report['failures'], report['pending'], report['kept']), ({}, [], []))
        result = campaign.close(m, store, self.call)
        self.assertTrue(result['empty'], result)
        self.assertFalse(store.bucket_exists())
        return report

    def test_one_command_runs_to_the_end_in_the_cluster_with_a_bucket_scoped_key(self):
        bucket = E['CAMPAIGN_STORE_SCOPED_BUCKET']
        m = self.manifest('k1', bucket, [{'name': 'ok', 'options': {'seconds': 12}},
                                         {'name': 'bad', 'options': {'seconds': 3, 'exitCode': 1}}])
        self.apply(m, who='CAMPAIGN_STORE_SCOPED')
        self.wait(lambda: self.job(m).get('succeeded'), 400, 'the controller Job')
        states = {k: v['state'] for k, v in self.statuses(m).items()}
        self.assertEqual(states, {'ok': 'scored', 'bad': 'failed'})
        before = campaign.census(m, self.store(bucket), self.call)
        self.assertFalse(before['empty'])
        self.assertIn('bucket', before['billable'])
        with tempfile.TemporaryDirectory() as out:
            self.finish(m, out)
            log = (Path(out) / 'ok/attempt-1/files/runtime/packet/load/k6.log').read_text().splitlines()
            self.assertEqual(len(log), 12)
            cleanup = json.loads((Path(out) / 'ok/attempt-1/files/campaign-cleanup.json').read_text())
            self.assertEqual((cleanup['verdict'], cleanup['by']), ('CLEANED', 'supervisor'))

    def test_a_killed_controller_resumes_and_reruns_the_interrupted_case_in_a_fresh_namespace(self):
        m = self.manifest('k2', 'lane9-k2', [{'name': 'first', 'options': {'seconds': 3}},
                                             {'name': 'long', 'options': {'seconds': 45}}])
        self.apply(m)
        self.wait(lambda: self.k('-n', 'bench-control', 'get', 'job', 'case-supervisor-k2-long-a1', check=False).returncode == 0
                  and self.k('get', 'namespace', 'ns-k2-long-a1', check=False).returncode == 0, 300, 'the long case and its supervisor')
        time.sleep(8)   # some evidence uploaded progressively
        pod = self.k('-n', 'bench-control', 'get', 'pods', '-l', 'nightscout.org/campaign=k2', '-o',
                     'jsonpath={.items[?(@.metadata.labels.app\\.kubernetes\\.io/name=="campaign-controller")].metadata.name}').stdout.split()
        self.assertEqual(len(pod), 1)
        self.k('-n', 'bench-control', 'delete', 'pod', pod[0], '--grace-period=1')
        self.wait(lambda: self.job(m).get('succeeded'), 500, 'the resumed controller')
        st = self.statuses(m)
        self.assertEqual(st['first']['state'], 'scored')
        self.assertEqual(len(st['first']['attempts']), 1)   # finished before the kill: not rerun
        long = st['long']
        self.assertEqual([(a['runId'], a['state'], a.get('reason')) for a in long['attempts']],
                         [('k2-long-a1', 'UNMEASURED', 'controller-interrupted'), ('k2-long-a2', 'scored', None)])
        self.assertEqual(long['state'], 'scored')
        self.assertNotEqual(long['attempts'][0]['controllerPod'], long['attempts'][1]['controllerPod'])
        with tempfile.TemporaryDirectory() as out:
            self.finish(m, out)
            note = json.loads((Path(out) / 'long/attempt-1/files/controller-interrupted.json').read_text())
            self.assertEqual((note['cleanup']['verdict'], note['cleanup']['reason']), ('CLEANED', 'heartbeat-stale'))
            # progressive upload: the interrupted attempt kept what reached the store before the kill
            self.assertTrue((Path(out) / 'long/attempt-1/files/runtime/packet/load/window.json').is_file())

    def test_a_controller_that_never_returns_still_has_its_case_cleaned_and_recorded(self):
        m = self.manifest('k3', 'lane9-k3', [{'name': 'orphan', 'options': {'seconds': 200}}])
        self.apply(m)
        self.wait(lambda: self.k('-n', 'bench-control', 'get', 'job', 'case-supervisor-k3-orphan-a1', check=False).returncode == 0,
                  300, 'the supervisor')
        self.k('-n', 'bench-control', 'delete', 'job', 'campaign-k3', '--cascade=foreground', '--wait=true')
        result = self.wait(lambda: self.k('-n', 'bench-control', 'get', 'configmap', 'case-cleanup-k3-orphan-a1', '-o', 'json',
                                          check=False).stdout, 200, 'the supervisor result')
        doc = json.loads(json.loads(result)['data']['result'])
        self.assertEqual((doc['verdict'], doc['reason']), ('CLEANED', 'heartbeat-stale'))
        self.assertEqual(self.k('get', 'namespace', 'ns-k3-orphan-a1', '--ignore-not-found=true', '-o', 'name').stdout, '')
        store = self.store('lane9-k3')
        self.assertEqual(self.statuses(m)['orphan']['state'], 'running')
        with tempfile.TemporaryDirectory() as out:
            report = campaign.collect(store, 'k3', out)
            self.assertEqual(report['pending'], ['orphan'])   # never sealed: collect leaves it
        census = campaign.census(m, store, self.call)
        self.assertGreater(census['billable']['bucket'][0]['objects'], 0)   # the census sees what is left
        self.assertTrue(any(x.startswith('jobs/case-supervisor-') for x in census['billable']['controlObjects']))
        with self.assertRaisesRegex(campaign.Refused, 'BUCKET_NOT_EMPTY'):
            campaign.close(m, store, self.call)
        for o in store.list(''):   # an operator's decision for an abandoned campaign; here, the test's teardown
            store.delete(o['key'])
        self.assertTrue(campaign.close(m, store, self.call)['empty'])

    def test_the_admission_policy_confines_the_controller_to_its_runs(self):
        m = self.manifest('k4', 'lane9-k4', [{'name': 'x', 'options': {'seconds': 1}}])
        self.k('create', 'namespace', 'lane9-foreign')
        self.addCleanup(self.k, 'delete', 'namespace', 'lane9-foreign', '--wait=false', check=False)
        self.apply(m)
        self.wait(lambda: self.job(m).get('succeeded'), 300, 'the controller Job')
        sa = ['--as=system:serviceaccount:bench-control:campaign-k4']
        ns = lambda name, label: json.dumps({'apiVersion': 'v1', 'kind': 'Namespace',
                                             'metadata': {'name': name, 'labels': {'nightscout.org/run-id': label}}})
        self.assertIn('writes only its own', self.k(*sa, 'delete', 'namespace', 'lane9-foreign', check=False).stderr)
        self.assertIn('writes only its own', self.k(*sa, 'create', '-f', '-', stdin=ns('lane9-other', 'k5-x-a1'), check=False).stderr)
        self.assertIn('writes only its own', self.k(*sa, '-n', 'lane9-foreign', 'create', 'configmap', 'x', check=False).stderr)
        self.assertEqual(self.k(*sa, 'create', '-f', '-', stdin=ns('ns-k4-x-a9', 'k4-x-a9'), check=False).returncode, 0)
        self.assertEqual(self.k(*sa, '-n', 'ns-k4-x-a9', 'create', 'configmap', 'x', check=False).returncode, 0)
        self.assertEqual(self.k(*sa, 'delete', 'namespace', 'ns-k4-x-a9', check=False).returncode, 0)
        with tempfile.TemporaryDirectory() as out:
            self.finish(m, out)
        # after close the identity has no policy and no binding: its writes are refused by RBAC instead
        self.assertNotEqual(self.k(*sa, '-n', 'lane9-foreign', 'create', 'configmap', 'y', check=False).returncode, 0)

    def test_a_workstation_fixture_record_restores_from_bench_control(self):
        import fixture_catalog
        import fixture_copy
        with tempfile.TemporaryDirectory() as tmp:
            key = fixture_catalog.key(tenants=1000, image='sha256:' + 'c' * 64, postgres_image='sha256:' + 'd' * 64,
                                      schema='migrations-tree:kind', transport='writer-driven')
            catalog = fixture_catalog.Catalog(Path(tmp) / 'ws/catalog.json')
            directory = catalog.reserve(key, 'kubernetes')
            directory.mkdir(mode=0o700)
            parts = fixture_copy.PARTS
            (directory / fixture_copy.MANIFEST).write_text(json.dumps({'version': 1, 'fixtureId': 'kind-seed', 'driver': 'd',
                'handles': dict.fromkeys(parts, 'h'), 'sizes': dict.fromkeys(parts, '1Gi'), 'seedContents': dict.fromkeys(parts, 'c'),
                'storageClass': 's', 'snapshotClass': 'v'}))
            (directory / fixture_copy.SECRETS).write_text(json.dumps([{'name': 'ns-ca', 'type': 'Opaque', 'data': {'k': 'dg=='}}]))
            for f in (fixture_copy.MANIFEST, fixture_copy.SECRETS):
                (directory / f).chmod(0o600)
            catalog.register(key, 'kubernetes', {'fixtureId': 'kind-seed', 'volumeSnapshotContents': {}, 'providerSnapshots': {}, 'seedCase': 'x'})
            digest = fixture_catalog.digest(key)
            self.k('create', 'namespace', 'bench-control', check=False)
            self.addCleanup(self.k, '-n', 'bench-control', 'delete', 'configmap,secret', 'fixture-' + digest, '--ignore-not-found=true')
            campaign.catalog_import(digest, Path(tmp) / 'ws/catalog.json', self.call)
            path = campaign.sync_catalog(self.call, Path(tmp) / 'pod/catalog')
            hit = fixture_catalog.Catalog(path).lookup(key, 'kubernetes')
            self.assertEqual(fixture_copy.read_manifest(hit['directory'])['fixtureId'], 'kind-seed')


if __name__ == '__main__':
    unittest.main()
