"""Frozen owner inputs and per-allocation preflight are independent contracts."""
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import tarfile
import unittest
from types import SimpleNamespace
from test_adapter import fixture

import kube_adapter as k
import experiment
import frozen
import primer_options


class Frozen(unittest.TestCase):
    def test_render_check_partition_keeps_native_policy_and_unexpected_jobs_visible(self):
        check = self.root/'bindings/kubernetes/check'
        check.mkdir(parents=True)
        (check/'invariants.js').write_text("""
          module.exports={checks:all=>[{name:'native-partition',failures:
            all.some(x=>x.kind==='NetworkPolicy'&&x.metadata.name==='native-load-to-edge') &&
            all.some(x=>x.kind==='ConfigMap'&&x.metadata.name==='application') &&
            !all.some(x=>x.kind==='Job') ? [] : ['wrong partition']}]};
        """)
        receipt=self.ref('binding.json',{'files':{}})
        render=self.root/'render.json';inventory=self.root/'inventory.json'
        policy={'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'native-load-to-edge'}}
        job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'k6'}}
        contents={'application':{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'application'}},
                  'nativeLoadResources':[job,policy]}
        k.write(render,contents);k.write(inventory,{'nativeLoad':{'version':1}})
        instance={'render':str(render),'inventory':str(inventory),'bindingReceipt':receipt}
        self.assertEqual(experiment.render_checks(instance),['native-partition'])
        contents['nativeLoadResources'].append(dict(job,metadata={'name':'unaccounted'}))
        k.write(render,contents)
        with self.assertRaisesRegex(k.Refused,'UNSUPPORTED_RENDER:native-partition'):
            experiment.render_checks(instance)
        contents['nativeLoadResources'].pop();k.write(render,contents)
        self.assertEqual(experiment.render_checks(instance),['native-partition'])

    def test_split_candidate_pin_uses_hashed_binding_and_refuses_contract_tamper(self):
        package = self.root/'bindings/kubernetes/assets'
        package.mkdir(parents=True)
        asset = package/'source-contract.json'
        contract = {'platformVerification':'startup-v4','sourceAcceptance':'PENDING',
                    'nativeCatalogueSha256':'1'*64,'localImageId':self.image}
        k.write(asset, contract)
        receipt = self.ref('binding.json', {'sourceContractSha256':k.digest(asset),
                                           'files':{'assets/source-contract.json':k.digest(asset)}})
        inventory = {'workloads':{'verification':{}}}
        pin = experiment.candidate_pin(inventory, receipt)
        self.assertEqual(pin['verificationJob'], 'verification')
        self.assertEqual(pin['imageConfigId'], self.image)
        self.assertEqual(pin['platformVerification'], 'startup-v4')
        k.write(asset, dict(contract, localImageId='sha256:'+'0'*64))
        with self.assertRaisesRegex(k.Refused, 'CANDIDATE_SOURCE_IMAGE_CHANGED'):
            experiment.candidate_pin(inventory, receipt)
        k.write(asset, contract)
        self.assertEqual(experiment.candidate_pin(inventory, receipt), pin)
        self.assertEqual(experiment.candidate_pin({'candidateContract':pin}, {}), pin)

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

    def test_source_receipt_provenance_is_recorded_not_reproved(self):
        baseline = frozen.source(self.manifest)
        self.assertEqual(baseline['sourceAcceptance'], 'PENDING')
        # Receipt words and cross-receipt pairs no longer refuse a run.
        for value in (dict(self.pending, coreCommit='a'*40), dict(self.pending, status='ACCEPTANCE_SELECTION'),
                      dict(self.pending, imageReceiptSha256='a'*64)):
            other = frozen.source(dict(self.manifest, sourceReceipt=self.ref('other', value)))
            self.assertEqual({**other, 'diagnosticSha256': None}, {**baseline, 'diagnosticSha256': None})
        # A PASS receipt for another image never labels this source PASS.
        other = dict(self.pending, kind='joined-acceptance', status='PASS', imageId='sha256:'+'a'*64)
        self.assertEqual(frozen.source(dict(self.manifest, sourceReceipt=self.ref('other', other)))['sourceAcceptance'], 'PENDING')
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_CHANGED'):
            frozen.source(dict(self.manifest, sourceReceipt=dict(self.manifest['sourceReceipt'],sha256='0'*64)))
        selected = {**baseline, 'nativeCatalogueSha256': '7'*64}
        self.assertEqual(frozen.contract(self.manifest, {**selected, 'coreCommit': 'b'*40}), baseline)
        with self.assertRaisesRegex(ValueError, 'CONTRACT_CONFIGURATION_CHANGED'):
            frozen.contract(self.manifest, {**selected, 'localImageId': 'sha256:'+'b'*64})

    def test_native_binding_inputs_skip_legacy_patch_and_keep_capture_protocol(self):
        from unittest.mock import patch
        selected = frozen.source(self.manifest)
        for version, captured, job in ((None, None, None), (1, 1, None), (1, None, None),
                                      (1, 1, 'verification'), (1, 1, 'dropped')):
            supported = dict(selected, commands={}, postgresIdentities={}, nativeCatalogueSha256='7'*64,
                             sourceFilesSha256={})
            if job:
                supported['verificationJob']='verification'
            if version is not None:
                supported['bindingInputsVersion'] = version
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode='w') as output:
                payload = json.dumps(supported).encode()
                member = tarfile.TarInfo('bindings/kubernetes/assets/source-contract.json')
                member.size = len(payload)
                output.addfile(member, io.BytesIO(payload))
            calls = []
            out = self.root/('materialized-'+str(version)+'-'+str(captured)+'-'+str(job))
            def git(argv, **_):
                if argv[3:5] == ['rev-parse', 'HEAD']:
                    return selected['deployCommit'].encode()
                if argv[3] == 'status':
                    return b''
                if argv[3] == 'show':
                    return b'synthetic prime source'
                if argv[3] == 'archive':
                    return archive.getvalue()
                self.fail(argv)
            def execute(argv, **_):
                calls.append(argv)
                if str(argv[1]).endswith('source-equivalence.py'):
                    path = out/'bindings/kubernetes/assets/source-contract.json'
                    measured = json.loads(path.read_bytes())
                    if job=='dropped':
                        measured.pop('verificationJob',None)
                    if captured is None:
                        measured.pop('bindingInputsVersion', None)
                    k.write(path, measured)
                return SimpleNamespace(returncode=0)
            with patch.object(experiment.subprocess, 'check_output', side_effect=git), \
                 patch.object(experiment.subprocess, 'run', side_effect=execute):
                if job=='dropped' or version == 1 and captured is None:
                    with self.assertRaisesRegex(k.Refused, 'CANDIDATE_VERIFICATION_JOB_CHANGED' if job else 'BINDING_INPUT_PROTOCOL_CHANGED'):
                        experiment.materialize(self.manifest, '/synthetic/binding', '/synthetic/deploy', out)
                    self.assertFalse((out/'binding.json').exists())
                else:
                    experiment.materialize(self.manifest, '/synthetic/binding', '/synthetic/deploy', out)
                    receipt = k.document(out/'binding.json')
                    self.assertEqual(any(argv[:2] == ['git', 'apply'] for argv in calls), version is None)
                    if version == 1:
                        self.assertEqual((receipt['bindingInputsVersion'], receipt['patchApplied']), (1, False))

    def test_selected_primer_requires_new_source_proof_and_preserves_exact_inputs(self):
        options={'concurrency':64,'maxTenants':20000}
        manifest={**self.manifest,'profile':{'phases':{'primerOptions':options}}}
        selected=frozen.source(manifest)
        self.assertEqual(selected['primerOptions'],options)
        fit={**selected,'nativeCatalogueSha256':'7'*64,'sourceFilesSha256':{'prime.js':'8'*64}}
        with self.assertRaisesRegex(ValueError,'PRIMER_OPTION_SOURCE_UNSUPPORTED'):
            frozen.contract(manifest,fit)
        fit['primerOptionProtocol']=primer_options.PROTOCOL
        self.assertEqual(frozen.contract(manifest,fit),selected)
        from unittest.mock import patch
        with patch.object(experiment,'workload',return_value=manifest['profile']):
            with self.assertRaisesRegex(k.Refused,'PRIMER_OPTIONS_AWAIT_PRIMER_REQUIRED'):
                experiment.prepare(self.ref('primer-intent',manifest)['path'],{},self.root/'new-packet')
        self.assertFalse((self.root/'new-packet').exists())
        with self.assertRaisesRegex(ValueError,'CONTRACT_CONFIGURATION_CHANGED'):
            frozen.contract(manifest,{**fit,'primerOptions':{'concurrency':33,'maxTenants':20000}})
        self.assertEqual(frozen.contract(manifest,fit),selected)

    def test_authored_publisher_job_wait_is_source_bound(self):
        manifest={**self.manifest,'profile':{'phases':{'startupWindows':{'kubernetes':{'jobCompleteSeconds':120}}}}}
        selected=frozen.source(manifest)
        self.assertEqual(selected[frozen.JOB_COMPLETE],120)
        selected['nativeCatalogueSha256']='7'*64
        with self.assertRaisesRegex(frozen.Refused,'CONTRACT_CONFIGURATION_CHANGED'):
            frozen.contract(manifest,{**selected,frozen.JOB_COMPLETE:30})
        frozen.contract(manifest,selected)
        script=self.root/'scripts/secrets.sh';script.parent.mkdir()
        source='k wait --for=condition=complete job/provision --timeout=30s >/dev/null\n'
        script.write_text(source)
        experiment.bind_job_completion_wait(self.root,selected)
        self.assertEqual(script.read_text(),source.replace('30s','120s'))

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
