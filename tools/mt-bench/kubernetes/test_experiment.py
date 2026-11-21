"""Frozen owner inputs and per-allocation preflight are independent contracts."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
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
        render=self.root/'render.json';inventory=self.root/'inventory.json'
        policy={'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'native-load-to-edge'}}
        job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'k6'}}
        contents={'application':{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'application'}},
                  'nativeLoadResources':[job,policy]}
        k.write(render,contents);k.write(inventory,{'nativeLoad':{'version':1}})
        instance={'render':str(render),'inventory':str(inventory),'binding':str(self.root)}
        self.assertEqual(experiment.render_checks(instance),['native-partition'])
        contents['nativeLoadResources'].append(dict(job,metadata={'name':'unaccounted'}))
        k.write(render,contents)
        with self.assertRaisesRegex(k.Refused,'UNSUPPORTED_RENDER:native-partition'):
            experiment.render_checks(instance)
        contents['nativeLoadResources'].pop();k.write(render,contents)
        self.assertEqual(experiment.render_checks(instance),['native-partition'])

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.pair = dict(core='1'*40, deploy='2'*40)
        self.image = 'sha256:'+'3'*64
        # bf55167272: the run's candidate comes from run parameters (image references,
        # digests and labelled commits); no source, build or delivery receipt is read.
        self.candidate = dict(app='registry.example.test/app@sha256:'+'3'*64, appImageId=self.image,
                              postgres='registry.example.test/postgres@sha256:'+'6'*64,
                              postgresImageId='sha256:'+'6'*64,
                              coreCommit=self.pair['core'], deployCommit=self.pair['deploy'])
        self.manifest = dict(version=1, kind='k8s-frozen-experiment', candidate=self.candidate,
                             bindingCommit='5'*40)

    def ref(self, name, value):
        p = self.root/name
        k.write(p,value)
        return dict(path=str(p), sha256=k.digest(p))

    def test_candidate_digest_is_run_identity_and_commits_are_recorded_not_compared(self):
        # brittle-check-removal: run identity is the image digest plus the run configuration.
        baseline = frozen.source(self.manifest)
        self.assertEqual((baseline['localImageId'], baseline['sourceAcceptance']), (self.image, 'PENDING'))
        # A candidate without digest-pinned references or full commits refuses.
        for field, value in (('app', 'registry.example.test/app:latest'), ('appImageId', 'sha256:short'),
                             ('coreCommit', 'abc'), ('postgres', None)):
            with self.subTest(field=field), self.assertRaisesRegex(frozen.Refused, 'K8S_EXPERIMENT_CANDIDATE'):
                frozen.source(dict(self.manifest, candidate=dict(self.candidate, **{field: value})))
        with self.assertRaisesRegex(frozen.Refused, 'FROZEN_ACCEPTANCE_REQUIRED'):
            frozen.source(dict(self.manifest, tier='acceptance'))
        selected = {**baseline, 'nativeCatalogueSha256': '7'*64}
        self.assertEqual(frozen.contract(self.manifest, {**selected, 'coreCommit': 'b'*40}), baseline)
        with self.assertRaisesRegex(ValueError, 'CONTRACT_CONFIGURATION_CHANGED'):
            frozen.contract(self.manifest, {**selected, 'localImageId': 'sha256:'+'b'*64})
        self.assertEqual(frozen.contract(self.manifest, selected), baseline)

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

    def test_ack_budget_binds_package_and_changes_only_ack_field(self):
        manifest = {**self.manifest, frozen.ACK_BUDGET: 60000}
        selected = frozen.source(manifest)
        baseline = frozen.source(self.manifest)
        self.assertEqual(selected, {**baseline, frozen.ACK_BUDGET: 60000})
        for invalid in (0, True, 1.5, 2**63):
            with self.assertRaisesRegex(ValueError, 'PGSTREAM_ACK_BUDGET'):
                frozen.source({**manifest, frozen.ACK_BUDGET: invalid})
        selected['nativeCatalogueSha256'] = '7'*64
        with self.assertRaisesRegex(ValueError, 'PGSTREAM_ACK_UNDECLARED'):
            frozen.contract(self.manifest, selected)
        wrong = {**selected, frozen.ACK_BUDGET: 10000}
        with self.assertRaisesRegex(ValueError, 'CONTRACT_CONFIGURATION_CHANGED'):
            frozen.contract(manifest, wrong)
        script = self.root/'scripts/secrets.sh'
        script.parent.mkdir()
        script.write_text('''#!/usr/bin/env bash
publish() {
  test -f "$work/primer/expected-verification.json"
  k create secret generic ns-config-pgstream --from-file=pgstream.yaml="$work/pgstream/pgstream.yaml" >/dev/null
  k wait --for=condition=complete job/provision --timeout=30s >/dev/null
}
''')
        experiment.bind_ack_publisher(self.root, selected)
        subprocess.run(['bash', '-n', script], check=True)
        self.assertIn('pgstream.effective.yaml', script.read_text())
        with self.assertRaisesRegex(k.Refused, 'PGSTREAM_ACK_PUBLISHER_CHANGED'):
            experiment.bind_ack_publisher(self.root, selected)
        source = self.root/'wire.json'
        config = dict(source=dict(publicSyntheticFixture=True),target=dict(webhooks=dict(notifier=dict(
            client_timeout=2000, worker_count=1, strict_mode=True,
            backoff=dict(constant=dict(max_retries=1,interval=50)),transaction_batch=dict(max_rows=4000)))))
        k.write(source, config)
        contract = self.ref('contract.json', selected)
        output = self.root/'effective.yaml'
        command = ['python3', '-B', str(self.root/frozen.ACK_PACKAGE[0]), contract['path'], str(source), str(output)]
        evidence = json.loads(subprocess.check_output(command))
        self.assertEqual(evidence, {'sourceTimeoutMs': 2000, 'effectiveTimeoutMs': 60000,
                                   'sourceWireSha256': k.digest(source), 'effectiveWireSha256': k.digest(output),
                                   'sourceContractSha256': contract['sha256']})
        result = k.document(output)
        result['target']['webhooks']['notifier']['client_timeout'] = 2000
        self.assertEqual(result, config)
        self.assertEqual(k.document(source), config)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        duplicate = subprocess.run(command, capture_output=True)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(duplicate.stderr.strip(), b'K8S_PGSTREAM_ACK_PUBLISH_FAILED')

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
