"""Prove the native sidecar publishes sanitized writer data before acknowledgment."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

import kube_adapter as k
import native_files
import native_load
from test_native_files import configured
from test_native_load import TENANTS

VOLUME = {'volumeName': 'capacity-example', 'storageClassName': '', 'storage': '64Mi'}
POD_UID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'


def synthetic(run):
    private = 'synthetic-private-value'
    event = {'event': 'm7-input-accepted', 'run': run, 'domain': 'entries', 'tenant': TENANTS[0]['id'],
             'key': '1700000000000', 'acceptedAtMs': 1700000000001, 'requestToAcceptanceMs': 1,
             'extra': private}
    log = f'url=https://example.test/?token={private}\n' + json.dumps({'msg': json.dumps(event)})
    summary = {'metrics': {'writes_ok': {'count': 1, 'thresholds': {private: True}},
                           'writes_ok{kind:entries}': {'count': 1}, 'writes_uncertain': {'count': 0},
                           'm7_http_completed{http_shape:w_sgv,status:201}': {'count': 1},
                           f'http_req_duration{{url:{private}}}': {'avg': 42}}}
    return {'k6.log': log, 'k6-summary.json': json.dumps(summary)}


class WriterPublication(unittest.TestCase):
    def test_selection_only_mounts_on_exporter_and_claim_requires_prebound_retained_pv(self):
        c, job, options = configured()
        c['nativeLoad'] = {'writerPublication': VOLUME}
        job, secret, receipt = native_load.package(c, job, b'// synthetic\n', TENANTS, **options)
        pod = job['spec']['template']['spec']
        self.assertTrue(json.loads(secret['stringData']['export.json'])['writerPublication'])
        self.assertEqual(receipt['writerPublication'], VOLUME)
        self.assertIn('native-publication.cjs', secret['stringData'])
        self.assertEqual([container['name'] for container in pod['containers']
                          if any(m['name'] == 'writer-publication' for m in container['volumeMounts'])], ['artifact-exporter'])
        ref = {'namespace': c['namespace'], 'name': 'writer-publication'}
        pv = {'metadata': {'name': VOLUME['volumeName']}, 'status': {'phase': 'Available'},
              'spec': {'accessModes': ['ReadWriteOnce'], 'claimRef': ref, 'capacity': {'storage': '64Mi'},
                       'persistentVolumeReclaimPolicy': 'Retain'}}
        claim = lambda obj: native_files.publication_claim(VOLUME, c['namespace'], c['runId'], obj)
        self.assertEqual(claim(pv)['spec']['volumeName'], VOLUME['volumeName'])
        self.assertEqual(claim(pv)['spec']['storageClassName'], '')
        for field, value in [('claimRef', {**ref, 'uid': POD_UID}), ('persistentVolumeReclaimPolicy', 'Delete'),
                             ('claimRef', {**ref, 'namespace': 'peer'}), ('capacity', {'storage': '32Mi'}),
                             ('volumeMode', 'Block'), ('storageClassName', 'different'), ('accessModes', ['ReadOnlyMany'])]:
            with self.subTest(field=field, value=value), self.assertRaises(k.Refused):
                changed = copy.deepcopy(pv)
                changed['spec'][field] = value
                claim(changed)
        with self.assertRaises(k.Refused):
            claim(None)

    def test_publish_before_ack_replay_identity_and_partial_evidence(self):
        script = k.HERE / 'native-artifacts.cjs'
        run = 'synthetic-load'
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = [Path(tmp) / name for name in ('out', 'retained')]
            source.mkdir()
            dest.mkdir()
            for name, data in synthetic(run).items():
                (source / name).write_text(data)
            cfg = {'runId': run, 'files': {name: 65536 for name in synthetic(run)},
                   'seconds': 10, 'writerPublication': True}
            (source / 'export.json').write_text(json.dumps(cfg))
            (source / 'exit-code').write_text('0\n')
            env = dict(os.environ, NS_NATIVE_OUTPUT=str(source), NS_NATIVE_EXPORT_CONFIG=str(source / 'export.json'),
                       NS_PUBLICATION_ROOT=str(dest), NS_PUBLICATION_POD_UID=POD_UID)
            hold = subprocess.Popen(['node', script, 'hold'], env=env)
            writer = dest / run / POD_UID / 'writer'
            try:
                deadline = time.monotonic() + 5
                while not (source / 'artifacts.json').exists() and time.monotonic() < deadline:
                    time.sleep(.03)
                record = json.loads((writer / 'publication.json').read_text())
                self.assertEqual(record['status'], 'complete')
                self.assertEqual(set(record['files']), {'k6.log', 'k6-summary.json'})
                self.assertIsNone(hold.poll())  # No exec or ack was issued.
                for name, meta in record['files'].items():
                    payload = (writer / name).read_bytes()
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), meta['sha256'])
                    self.assertNotIn(b'synthetic-private-value', payload)
                summary = json.loads((writer / 'k6-summary.json').read_text())
                self.assertEqual(summary['metrics']['m7_http_completed{http_shape:w_sgv,status:201}'], {'count': 1})
                event = json.loads(json.loads((writer / 'k6.log').read_text())['msg'])
                self.assertEqual(event['tenant'], TENANTS[0]['id'])
                self.assertNotIn('extra', event)
                (source / 'native-artifacts.json').write_bytes((source / 'artifacts.json').read_bytes())
            finally:
                hold.terminate()
                hold.wait(timeout=3)
            def replay(uid=POD_UID):
                return subprocess.run(['node', script, 'publish', source, run, uid, dest],
                                      capture_output=True, timeout=5)
            custody = {'kind': 'm7-kubernetes-k6-job-v1', 'runId': run, 'podUid': POD_UID,
                       'artifactSource': {'podUid': POD_UID}}
            (source / 'native-load.json').write_text(json.dumps(custody))
            self.assertEqual(json.loads(replay().stdout), record)
            self.assertIn(b'CUSTODY', replay('11111111-2222-4333-8444-555555555555').stderr)
            (source / 'k6.log').unlink()
            self.assertIn(b'CONFLICT', replay().stderr)
            self.assertEqual(json.loads((writer / 'publication.json').read_text()), record)
            uid = '11111111-2222-4333-8444-555555555555'
            (source / 'native-load.json').write_text(json.dumps(dict(custody, podUid=uid, artifactSource={'podUid': uid})))
            partial = replay(uid)
            self.assertEqual(partial.returncode, 78)
            self.assertEqual(json.loads(partial.stdout)['problems'], {'k6.log': 'invalid-or-missing'})
