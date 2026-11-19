"""Native load transport controls; synthetic Kubernetes replies, no live actors."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import execute
import native_load as n
import kube_adapter as k
from test_adapter import fixture

RUN = 'synthetic-kube-control-load'
SCRIPT = b'export default function () {}\n'
TENANTS = [{'id': ('1' if i == 0 else '2') * 8 + '-1111-4111-8111-' + ('1' if i == 0 else '2') * 12,
            'host': ('a' if i == 0 else 'b') + '.example.test', 'token': 'synthetic-token'} for i in range(2)]


def control():
    c, _, objects, _ = fixture()
    c.update(namespace='ns-synth-native-control', tenants=2,
             workload=dict(loadSeconds=120, offeredRps=2, logicalPollingClients=2, probeEveryMs=1000))
    c['deadlines']['workUntil'] = '2099-01-01T00:00:00Z'
    labels = {c['ownerLabel']: c['runId']}
    budget = copy.deepcopy(objects[1]['spec']['template']['spec']['containers'][0]['resources'])
    job = {'apiVersion': 'batch/v1', 'kind': 'Job',
           'metadata': {'name': 'k6', 'namespace': c['namespace'], 'labels': labels},
           'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 600,
                    'template': {'metadata': {'labels': labels}, 'spec': {
                        'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                        'containers': [{'name': 'k6', 'image': 'example.invalid/k6@sha256:' + '9' * 64,
                                        'args': ['run', '/inputs/workload.js'], 'resources': budget,
                                        'env': [{'name': 'BASE_URL', 'value': 'http://edge:8080'}],
                                        'securityContext': {'runAsNonRoot': True, 'readOnlyRootFilesystem': True,
                                                            'allowPrivilegeEscalation': False,
                                                            'capabilities': {'drop': ['ALL']}}}],
                        'volumes': [{'name': 'inputs', 'secret': {'secretName': 'ns-k6-inputs'}},
                                    {'name': 'tmp', 'emptyDir': {'sizeLimit': '16Mi'}}]}}}}
    return c, job


OPTIONS = dict(runid=RUN, seconds=300, run_start_ms=1900000000000, setup_seconds=10)


def frames(summary=None, *, runid=RUN):
    payload = json.dumps(summary or {'metrics': {'synthetic_counter': {'count': 2}}})
    parts = [payload[i:i+n.CHUNK_CHARS] for i in range(0, len(payload), n.CHUNK_CHARS)]
    return [dict(kind=n.KIND, runId=runid,
                 index=i, total=len(parts), text=part) for i, part in enumerate(parts)]


def logs(rows=None):
    return (json.dumps({'level': 'info', 'msg': json.dumps({'event': 'scenario-first-iteration',
                                                          'shape': 'w_sgv', 'atMs': 1900000000000})}) + '\n'
            + '\n'.join(json.dumps(row) for row in (rows if rows is not None else frames())) + '\n').encode()


class Kube:
    def __init__(self, c, *, failure=None):
        self.c, self.failure, self.calls, self.created = c, failure, [], []
        self.ns_reads = 0
        self.log = logs()

    def call(self, args, **kw):
        self.calls.append(args)
        if args[0] == 'create':
            self.created.append(json.loads(kw['data']))
            value = copy.deepcopy(self.created[-1]); value['metadata']['uid'] = 'owned-job'
            return json.dumps(value)
        if args[0] == 'wait' and self.failure == 'wait':
            raise RuntimeError('synthetic wait failure')
        return self.log if args[0] == 'logs' else ''

    def readback(self):
        job = copy.deepcopy(self.created[-1])
        job['metadata']['uid'] = 'owned-job'
        job['status'] = {'succeeded': 1, 'conditions': [{'type': 'Complete', 'status': 'True',
                         'lastTransitionTime': '2026-11-19T00:00:00Z'}]}
        pod = {'apiVersion': 'v1', 'kind': 'Pod',
               'metadata': {'name': 'k6-owned', 'namespace': self.c['namespace'], 'uid': 'owned-pod',
                            'labels': copy.deepcopy(job['spec']['template']['metadata']['labels']), 'ownerReferences': [
                                {'kind': 'Job', 'name': 'k6', 'uid': 'owned-job', 'controller': True}]},
               'spec': copy.deepcopy(job['spec']['template']['spec']),
               'status': {'phase': 'Succeeded', 'containerStatuses': [
                   {'name': 'k6', 'restartCount': 0, 'containerID': 'containerd://owned',
                    'imageID': 'containerd://sha256:' + '9' * 64,
                    'state': {'terminated': {'exitCode': 0}}}]}}
        if self.failure == 'exit':
            pod['status']['containerStatuses'][0]['state']['terminated']['exitCode'] = 1
        if self.failure == 'restart':
            pod['status']['containerStatuses'][0]['restartCount'] = 1
        if self.failure == 'foreign':
            pod['metadata']['ownerReferences'][0]['uid'] = 'peer-job'
        return job, pod

    def json(self, args, **kw):
        self.calls.append(args)
        if args[:2] == ['get', 'namespace']:
            self.ns_reads += 1
            return {'metadata': {'name': self.c['namespace'], 'uid': 'reassigned' if
                    self.failure == 'namespace' and self.ns_reads > 1 else 'owned-namespace',
                    'labels': {self.c['ownerLabel']: self.c['runId']}}}
        job, pod = self.readback()
        if args[:2] == ['get', 'job']:
            return job
        if args[:2] == ['get', 'pods']:
            return {'items': [pod, copy.deepcopy(pod)] if self.failure == 'duplicate' else [pod]}
        if args[:2] == ['get', 'pod']:
            if self.failure == 'replacement':
                pod['metadata']['uid'] = 'replacement'
            return pod
        raise AssertionError(args)


class NativeLoad(unittest.TestCase):
    def test_package_keeps_job_resources_placement_init_and_never_copies_ambient_env(self):
        c, job = control()
        original = copy.deepcopy(job)
        job['spec']['ttlSecondsAfterFinished'] = 20
        job['spec']['template']['spec']['nodeSelector'] = {'synthetic-node': 'owned'}
        with patch.dict(os.environ, {'SECRET_TOKEN': 'must-not-copy', 'OFFERED_RPS': 'wrong'}):
            rendered, secret, receipt = n.package(c, job, SCRIPT, TENANTS, **OPTIONS)
        pod = rendered['spec']['template']['spec']
        actor = pod['containers'][0]
        self.assertEqual(actor['resources'], original['spec']['template']['spec']['containers'][0]['resources'])
        self.assertEqual(pod['nodeSelector'], {'synthetic-node': 'owned'})
        env = {row['name']: row['value'] for row in actor['env']}
        self.assertEqual((env['BASE_URL'], env['OFFERED_RPS']), ('http://edge:8080', '2'))
        self.assertNotIn('SECRET_TOKEN', env)
        self.assertEqual(rendered['spec']['activeDeadlineSeconds'], OPTIONS['seconds'])
        self.assertNotIn('ttlSecondsAfterFinished', rendered['spec'])
        self.assertTrue(secret['immutable'])
        self.assertTrue(secret['stringData']['workload.js'].encode().startswith(SCRIPT))
        self.assertEqual(receipt['outcomeGate'], 'UNMEASURED')
        self.assertEqual(receipt['capacityAcceptance'], 'NOT_GRANTED')

    def test_configured_plan_requires_explicit_exporter_admission_before_actor_creation(self):
        c, job = control()
        c['workload']['driverPlan'] = dict(version=1, observer='scheduling-v1',
            scenarios={shape: {} for shape in workload_runtime.SHAPES})
        kube = Kube(c)
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(k.Refused, 'EXPORTER_RESOURCES_REQUIRED'):
                n.run(kube, c, job, SCRIPT, TENANTS, out, **OPTIONS)
        self.assertEqual(kube.calls, [])
        c['workload']['driverShards'] = 2
        with self.assertRaisesRegex(k.Refused, 'UNSUPPORTED:driverShards'):
            n.selection(c)

    def test_replay_authority_environment_and_deadline_controls_restore(self):
        c, job = control()
        changes = [
            (job['spec'], 'backoffLimit', 1, 'JOB_REPLAY_OR_AUTHORITY'),
            (job['spec'], 'parallelism', 2, 'JOB_REPLAY_OR_AUTHORITY'),
            (job['spec']['template']['spec'], 'hostNetwork', True, 'JOB_REPLAY_OR_AUTHORITY'),
            (job['spec']['template']['spec'], 'volumes', [{'name': 'host', 'hostPath': {'path': '/'}}], 'VOLUME_AUTHORITY'),
            (job['spec']['template']['spec']['containers'][0], 'env',
             [{'name': 'BASE_URL', 'value': 'http://127.0.0.1:8080'}], 'SERVICE_ADDRESS'),
            (job['spec']['template']['spec']['containers'][0], 'env',
             [{'name': 'BASE_URL', 'value': 'http://edge:8080'}, {'name': 'OFFERED_RPS', 'value': '999'}], 'ENVIRONMENT_CONFLICT'),
            (c['deadlines'], 'workUntil', '2000-01-01T00:00:00Z', 'WORK_DEADLINE'),
        ]
        for target, key, value, code in changes:
            old, existed = target.get(key), key in target
            target[key] = value
            kube = Kube(c)
            with tempfile.TemporaryDirectory() as out:
                with self.assertRaisesRegex(k.Refused, code):
                    n.run(kube, c, job, SCRIPT, TENANTS, out, **OPTIONS)
            self.assertEqual(kube.calls, [])
            if existed: target[key] = old
            else: del target[key]
            n.package(c, job, SCRIPT, TENANTS, **OPTIONS)

    def test_framing_and_identity_controls_restore(self):
        metric = {'metrics': {'large': {'count': 1, 'synthetic': 'x' * 20000}}}
        rows = frames(metric)
        self.assertEqual(n.decode(logs(rows), RUN)[1], metric)
        for changed, code in ((rows[:-1], 'INCOMPLETE'), (rows+rows, 'FRAMING'),
                              (list(reversed(rows)), 'FRAMING'), (frames(runid='peer'), 'BINDING'),
                              ([], 'INCOMPLETE')):
            with self.assertRaisesRegex(k.Refused, code):
                n.decode(logs(changed), RUN)
            self.assertEqual(n.decode(logs(rows), RUN)[1], metric)

    def test_complete_job_retains_reducer_inputs_and_still_cannot_claim_product_pass(self):
        c, job = control(); kube = Kube(c)
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch)
            receipt = n.run(kube, c, job, SCRIPT, TENANTS, out, **OPTIONS)
            self.assertEqual(receipt['capture'], 'CAPTURED')
            self.assertTrue(receipt['process']['complete'])
            self.assertEqual(receipt['outcomeGate'], 'UNMEASURED')
            self.assertEqual(k.document(out/'k6-summary.json')['metrics']['synthetic_counter']['count'], 2)
            self.assertIn(b'scenario-first-iteration', (out/'k6.log').read_bytes())
            for path in ('k6-native.log', 'k6.log', 'k6-summary.json'):
                self.assertEqual((out/path).stat().st_mode & 0o777, 0o600)
            self.assertEqual([r['kind'] for r in kube.created], ['Secret', 'Job'])
            self.assertTrue(all(call[0] != 'apply' for call in kube.calls))

    def test_restarted_writer_emits_terminal_summary_with_incomplete_continuity(self):
        c, job = control()
        with tempfile.TemporaryDirectory() as out:
            receipt = n.run(Kube(c, failure='restart'), c, job, SCRIPT, TENANTS, out, **OPTIONS)
            self.assertEqual(receipt['writerContinuity'], 'UNMEASURED')
            self.assertEqual(receipt['process']['restartCount'], 1)

    def test_failed_wait_exit_scope_replacement_and_duplicate_controls(self):
        for failure, code in [('wait', 'JOB_FAILED'), ('exit', 'JOB_FAILED'),
                              ('namespace', 'NAMESPACE_CHANGED'), ('replacement', 'POD_REPLACED'),
                              ('foreign', 'POD_CONTROLLER'), ('duplicate', 'POD_CENSUS')]:
            c, job = control(); kube = Kube(c, failure=failure)
            with tempfile.TemporaryDirectory() as out:
                with self.assertRaisesRegex(k.Refused, code):
                    n.run(kube, c, job, SCRIPT, TENANTS, out, **OPTIONS)
            with tempfile.TemporaryDirectory() as out:
                n.run(Kube(c), c, job, SCRIPT, TENANTS, out, **OPTIONS)

    def test_bridge_calls_existing_full_assessor_and_never_synthesizes_oracles(self):
        c, job = control()
        with tempfile.TemporaryDirectory() as scratch:
            d = Path(scratch); out = d/'load'; out.mkdir()
            (d/'workload.js').write_bytes(SCRIPT)
            n.run(Kube(c), c, job, SCRIPT, TENANTS, out, **OPTIONS)
            (out/'runid').write_text(RUN)
            baseline = {'namespace': {'uid': 'owned-namespace'}}
            with patch.object(k, 'active_baseline', return_value=baseline), \
                 patch.object(execute, 'assess_stage', side_effect=k.Refused('K8S_CLINICAL_UNMEASURED', 'UNMEASURED')) as full:
                with self.assertRaisesRegex(k.Refused, 'CLINICAL_UNMEASURED'):
                    n.assess_join(d, out, c, {'actual': 'objects'}, 'actual-client')
                full.assert_called_once_with(d, out, c, {'actual': 'objects'}, 'actual-client')
                self.assertFalse((out/'probe.json').exists())
            replaced = {'namespace': {'uid': 'different-namespace'}}
            with patch.object(k, 'active_baseline', return_value=replaced), patch.object(execute, 'assess_stage') as full:
                with self.assertRaisesRegex(k.Refused, 'ASSESSMENT_BINDING'):
                    n.assess_join(d, out, c, {}, None)
                full.assert_not_called()

    @unittest.skipUnless(os.environ.get('NS_NATIVE_K6_TEST_BINARY'), 'set NS_NATIVE_K6_TEST_BINARY for local binary proof')
    def test_actual_k6_exports_original_counter_and_event_envelope(self):
        binary = os.environ['NS_NATIVE_K6_TEST_BINARY']
        script = b'''import {Counter} from 'k6/metrics';
const count = new Counter('transport_control_count');
export const options = {iterations:2, thresholds:{transport_control_count:['count==2']}};
export default function(){count.add(1);console.log(JSON.stringify({event:'scenario-first-iteration',shape:'w_sgv',atMs:Date.now()}));}
'''
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)/'control.js'; path.write_bytes(n.summary_script(script, RUN))
            result = subprocess.run([binary, 'run', '--quiet', '--no-usage-report', '--address=',
                                     '--log-format=json', '--log-output=stdout', str(path)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events, summary = n.decode(result.stdout, RUN)
        self.assertEqual(summary['metrics']['transport_control_count']['count'], 2)
        self.assertEqual(summary['metrics']['transport_control_count']['thresholds']['count==2'], False)
        self.assertIn(b'scenario-first-iteration', events)


import workload_runtime

if __name__ == '__main__':
    unittest.main()
