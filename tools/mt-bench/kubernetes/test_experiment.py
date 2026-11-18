"""Frozen owner inputs and per-allocation preflight are independent contracts."""
import copy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from test_adapter import fixture

import kube_adapter as k
import experiment
import frozen


class Frozen(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.pair = dict(core='1'*40, deploy='2'*40)
        self.image = 'sha256:'+'3'*64
        self.build = dict(schemaVersion=1, status='BUILT_VERIFIED_LOCAL', localImageId=self.image,
                          coreCommit=self.pair['core'], deployCommit=self.pair['deploy'],
                          runtime=dict(binarySha256='4'*64, producerHelpSucceeded=True),
                          labels={'org.opencontainers.image.revision':self.pair['core'],
                                  'org.nightscout.deploy.revision':self.pair['deploy']})
        build = self.ref('build',self.build)
        self.pending = dict(status='FROZEN_DIAGNOSTIC_ONLY', sourceAcceptance='PENDING',
                            coreCommit=self.pair['core'], deployCommit=self.pair['deploy'], imageId=self.image,
                            imageReceiptSha256=build['sha256'], capacityAcceptance='NOT_GRANTED')
        self.manifest = dict(version=1, kind='k8s-frozen-experiment', sourceReceipt=self.ref('owner',self.pending),
                             buildReceipt=build, bindingCommit='5'*40, postgresImageId='sha256:'+'6'*64)

    def ref(self, name, value):
        p = self.root/name
        k.write(p,value)
        return dict(path=str(p), sha256=k.digest(p))

    def test_owner_receipt_is_distinct_from_build_and_selection(self):
        baseline = frozen.source(self.manifest)
        self.assertEqual(baseline['sourceAcceptance'], 'PENDING')
        cases = ((dict(self.pending, coreCommit='a'*40), 'SOURCE_PAIR'),
                 (dict(self.pending, imageId='sha256:'+'a'*64), 'SOURCE_IMAGE'),
                 (dict(self.pending, status='ACCEPTANCE_SELECTION'), 'SOURCE_RECEIPT'),
                 (dict(self.pending, imageReceiptSha256='a'*64), 'SOURCE_PAIR'))
        for value, code in cases:
            with self.assertRaisesRegex(ValueError, 'K8S_EXPERIMENT_'+code+'$'):
                frozen.source(dict(self.manifest, sourceReceipt=self.ref('bad',value)))
            self.assertEqual(frozen.source(self.manifest),baseline)
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_CHANGED'):
            frozen.source(dict(self.manifest, sourceReceipt=dict(self.manifest['sourceReceipt'],sha256='0'*64)))

    def test_independent_registry_bytes(self):
        receipts = {name:self.ref(name, dict(schemaVersion=2,mediaType='application/vnd.oci.image.manifest.v1+json',
                                             config=dict(digest=identity))) for name,identity in
                    [('app',self.image),('postgres',self.manifest['postgresImageId'])]}
        images = {name:'example.invalid/'+name+'@sha256:'+ref['sha256'] for name,ref in receipts.items()}
        delivery = dict(**images, appImageId=self.image, postgresImageId=self.manifest['postgresImageId'],
                        sourceCommit=self.pair['core'], imageDeployCommit=self.pair['deploy'],registryPlanChange=False,
                        transferCostApproved=True,registryManifests={name:r['path'] for name,r in receipts.items()})
        frozen.registry(delivery, images, self.manifest)
        with self.assertRaisesRegex(ValueError,'REGISTRY_CONFIG_CHANGED'):
            frozen.registry(dict(delivery,postgresImageId=self.image),images,self.manifest)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_CHANGED'):
            frozen.registry(dict(delivery,registryManifests=dict.fromkeys(images,receipts['app']['path'])),images,self.manifest)
        frozen.registry(delivery, images, self.manifest)

    def test_private_fresh_preflight_for_this_experiment(self):
        c = dict(runId='test',namespace='synthetic-test',experimentSha256='7'*64,pins=dict(renderSha256='8'*64))
        observed = dict(offline='PASS',commissioning='PREFLIGHT_ONLY',experiment=dict(
            runId=c['runId'], namespace=c['namespace'],experimentSha256=c['experimentSha256'],renderSha256=c['pins']['renderSha256']))
        experiment.require_preflight(observed,c)
        for field in observed['experiment']:
            altered = copy.deepcopy(observed)
            altered['experiment'][field] = 'foreign'
            with self.assertRaisesRegex(k.Refused,'PREFLIGHT_EXPERIMENT_CHANGED'):
                experiment.require_preflight(altered,c)
            experiment.require_preflight(observed,c)

    def test_verified_role_failure_keeps_its_classification(self):
        c, *_ = fixture()
        binary = self.root/'kubectl'
        binary.touch(mode=0o700)
        c['kubectl'] = str(binary)
        reply = SimpleNamespace(returncode=0,stdout=b'{}',stderr=b'')
        client = k.Client(c,lambda *args,**kw:reply)
        self.assertEqual(client.get('pods'),{})
        reply.returncode, reply.stderr = 1,b'EVALUATOR_SCOPE_UNSAFE'
        with self.assertRaisesRegex(k.Refused,'^EVALUATOR_SCOPE_UNSAFE$'):
            client.get('pods')
        reply.returncode, reply.stderr = 0,b''
        self.assertEqual(client.get('pods'),{})


    def test_observation_loss_stops_owned_native_worker(self):
        import sys
        import threading
        import execute
        c, *_ = fixture()
        failures = []
        timer = threading.Timer(.1, lambda: failures.append(k.Refused('K8S_NAMESPACE_UID_CHANGED')))
        with (self.root/'worker.log').open('wb') as output:
            timer.start()
            try:
                with self.assertRaisesRegex(k.Refused, 'NAMESPACE_UID_CHANGED'):
                    execute.finite(c, [sys.executable, '-c', 'import time; time.sleep(10)'],
                                   output=output, seconds=3, failures=failures)
            finally:
                timer.join()
            failures.clear()
            execute.finite(c, [sys.executable, '-c', 'print("restored")'], output=output, failures=failures)
        self.assertIn('restored', (self.root/'worker.log').read_text())
