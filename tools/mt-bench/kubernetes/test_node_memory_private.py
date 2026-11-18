"""Real private CLI/caller with pinned inert tools; no cluster access."""
import copy
from datetime import datetime, timezone
from decimal import localcontext
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import node_memory_private as p

Mi = 1024**2


class NodeMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.bin = self.root/'bin'; self.bin.mkdir()
        self.data = self.root/'data.private.json'; self.log = self.root/'calls.jsonl'
        self.node = {'metadata': {'name': 'synthetic-node', 'uid': 'synthetic-node-uid', 'resourceVersion': '1'},
                     'spec': {}, 'status': {'capacity': {'memory': '8Gi'}, 'allocatable': {'memory': '6Gi'},
                     'nodeInfo': {'bootID': 'synthetic-boot', 'kubeletVersion': 'v1.34.12', 'operatingSystem': 'linux'},
                     'conditions': [{'type': 'Ready', 'status': 'True'}, {'type': 'MemoryPressure', 'status': 'False'}]}}
        self.pods = {'items': [{'metadata': {'name': 'synthetic-pod', 'namespace': 'synthetic-system', 'uid': 'pod-uid'},
                                'spec': {'nodeName': 'synthetic-node', 'containers': [{'name': 'actor', 'resources': {
                                    'requests': {'cpu': '100m', 'memory': '512Mi'}}}]},
                                'status': {'phase': 'Running', 'containerStatuses': [{'name': 'actor',
                                    'containerID': 'containerd://synthetic', 'imageID': 'sha256:synthetic',
                                    'restartCount': 0, 'ready': True}]}}]}
        now = datetime.now(timezone.utc).isoformat()
        def memory(ws, limit):
            return {'time': now, 'workingSetBytes': ws*Mi, 'availableBytes': (limit-ws)*Mi, 'usageBytes': (ws+16)*Mi}
        self.summary = {'node': {'nodeName': 'synthetic-node', 'startTime': '2026-11-01T00:00:00Z',
                        'memory': memory(1024, 8192), 'systemContainers': [{'name': 'pods',
                        'startTime': '2026-11-01T00:00:00Z', 'memory': memory(256, 7168)}]},
                        'pods': [{'credential': 'RAW-SUMMARY-MUST-STAY-PRIVATE', 'memory': {'workingSetBytes': 1}}]}
        self.config = {'kubeletconfig': {'cgroupsPerQOS': True, 'cgroupDriver': 'systemd',
                       'enforceNodeAllocatable': ['pods'], 'cgroupRoot': '',
                       'kubeReserved': {'memory': '512Mi'}, 'systemReserved': {'memory': '512Mi'},
                       'evictionHard': {'memory.available': '1Gi'}, 'evictionSoft': {'memory.available': '1.5Gi'},
                       'evictionSoftGracePeriod': {'memory.available': '1m'},
                       'evictionMinimumReclaim': {'memory.available': '128Mi'},
                       'authentication': {'password': 'RAW-CONFIG-MUST-STAY-PRIVATE'}}}
        self.fixture = {'node': self.node, 'pods': self.pods, 'summary': self.summary, 'config': self.config}
        self.kubectl = self.bin/'kubectl'; self.guard = self.bin/'ro'
        self.kubectl.write_text('#!'+sys.executable+'\n'+'''import copy,json,os,sys
from pathlib import Path
d=json.loads(Path(os.environ['NODE_MEMORY_TEST_DATA']).read_text());args=sys.argv[1:]
if args[0:2]!=['--context','synthetic-context']:sys.exit(3)
guarded=os.environ.get('NODE_MEMORY_TEST_GUARDED')=='1'
if '--raw' in args:
 if guarded:sys.exit(3)
 path=args[args.index('--raw')+1]
 allowed={'/api/v1/nodes/synthetic-node/proxy/stats/summary':'summary','/api/v1/nodes/synthetic-node/proxy/configz':'config'}
 if path not in allowed:sys.exit(3)
 kind=allowed[path]
else:
 if not guarded or 'get' not in args:sys.exit(3)
 kind=args[args.index('get')+1]
 if kind not in ['node','pods']:sys.exit(3)
 if kind=='node' and args[args.index('node')+1]!='synthetic-node':sys.exit(3)
 if kind=='pods' and '--field-selector=spec.nodeName=synthetic-node' not in args:sys.exit(3)
log=Path(os.environ['NODE_MEMORY_TEST_LOG']);old=[json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
count=sum(x['kind']==kind for x in old)
with log.open('a') as f:f.write(json.dumps({'kind':kind,'guarded':guarded,'args':args})+'\\n')
fault=d.get('fault')
if fault=='api_failure':sys.stderr.write('RAW-ERROR-SECRET');sys.exit(3)
value=copy.deepcopy(d[kind])
if count:
 if fault=='node_uid' and kind=='node':value['metadata']['uid']='replaced'
 if fault=='boot' and kind=='node':value['status']['nodeInfo']['bootID']='rebooted'
 if fault=='census_uid' and kind=='pods':value['items'][0]['metadata']['uid']='replaced'
 if fault=='resource' and kind=='pods':value['items'][0]['spec']['containers'][0]['resources']['requests']['memory']='2Gi'
 if fault=='policy' and kind=='config':value['kubeletconfig']['evictionHard']['memory.available']='2Gi'
 if fault=='start' and kind=='summary':value['node']['systemContainers'][0]['startTime']='2026-11-02T00:00:00Z'
 if fault=='status_refresh':
  if kind=='node':value['metadata']['resourceVersion']='normal-heartbeat'
  if kind=='pods':value['items'][0]['status']['containerStatuses'][0]['ready']=False
 if fault=='usage_refresh' and kind=='summary':
  for m in [value['node']['memory'],value['node']['systemContainers'][0]['memory']]:m['workingSetBytes']+=1024;m['availableBytes']-=1024;m['usageBytes']+=1024
if fault=='lost_output':sys.exit(0)
sys.stdout.write(json.dumps(value))
'''); self.kubectl.chmod(0o700)
        self.guard.write_text('#!'+sys.executable+'\n'+'''import os,sys
from pathlib import Path
if sys.argv[1]!='kubectl' or '--raw' in sys.argv:sys.exit(3)
os.environ['NODE_MEMORY_TEST_GUARDED']='1'
os.execv(str(Path(__file__).with_name('kubectl')),['kubectl',*sys.argv[2:]])
'''); self.guard.chmod(0o700)
        self.scope = p.make_scope('synthetic-context', self.node, self.kubectl, self.guard,
                                  until=time.time()+300, max_age_seconds=120, max_skew_seconds=30)
        self.scopefile = self.root/'scope.private.json'
        self.refresh()
        self.environment = patch.dict(os.environ, NODE_MEMORY_TEST_DATA=str(self.data), NODE_MEMORY_TEST_LOG=str(self.log))
        self.environment.start(); self.addCleanup(self.environment.stop)

    def refresh(self):
        self.data.write_text(json.dumps(self.fixture)); self.data.chmod(0o600)
        self.scopefile.write_text(json.dumps(self.scope)); self.scopefile.chmod(0o600)
        self.ref = {'path': str(self.scopefile), 'sha256': p.sha(self.scopefile)}
        if self.log.exists():
            self.log.unlink()

    def collect(self):
        self.refresh()
        return p.collect(self.ref)

    def test_actual_cli_caller_fixed_gets_numeric_projection_and_privacy(self):
        answer = self.collect()
        self.assertEqual(answer['status'], 'MEASURED')
        self.assertEqual(answer['samples'][0]['pods']['workingSetBytes'], 256*Mi)
        self.assertEqual(answer['samples'][0]['pods']['reportedLocalLimitBytes'], 7168*Mi)
        self.assertEqual(answer['softReserve']['denominator'], 5)
        self.assertFalse(answer['policy']['ancestorCeilingsVerified'])
        raw = json.dumps(answer)
        self.assertNotIn('RAW-', raw); self.assertNotIn('authentication', raw)
        calls = [json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertEqual(len(calls), 8)
        self.assertEqual([x['kind'] for x in calls], ['node', 'pods', 'config', 'summary', 'summary', 'config', 'pods', 'node'])
        self.assertEqual(sum(x['guarded'] for x in calls), 4)
        self.assertTrue(all('get' in x['args'] for x in calls))

    def test_policy_hard_soft_grace_reclaim_and_separate_percentage_bases(self):
        answer = self.collect(); rows = answer['policy']['thresholds']
        self.assertEqual([(x['signal'], x['hard'], x['generated']) for x in rows],
                         [('allocatableMemory.available', True, True), ('memory.available', True, False),
                          ('memory.available', False, False)])
        self.assertEqual(rows[0]['recoveryThresholdBytes'], (1024+128)*Mi)
        self.assertEqual(rows[2]['graceNanoseconds'], 60*10**9)
        self.config['kubeletconfig']['evictionHard']['memory.available'] = '10%'
        rows = self.collect()['policy']['thresholds']
        self.assertEqual(rows[0]['thresholdBytes'], 751619288)
        self.assertEqual(rows[1]['thresholdBytes'], 858993472)

    def test_disabled_thresholds_and_quantity_equivalence(self):
        for selected in ('0%', '100%'):
            self.config['kubeletconfig']['evictionHard']['memory.available'] = selected
            self.assertFalse(any(x['hard'] for x in self.collect()['policy']['thresholds']))
        self.assertEqual(p.quantity('1Gi'), p.quantity('1024Mi'))
        self.assertEqual(p.quantity('1e3'), 1000)
        self.assertEqual(p.quantity('0.1'), 1)
        self.assertEqual(p.duration('1m0.5s'), 60500000000)
        self.assertEqual(p.duration('.5s'), 500000000)
        self.assertEqual(p.threshold('150%', 1000, reclaim=True), 1500)
        for value in ('1e3Mi', '1MiB'):
            with self.assertRaises(p.Refused): p.quantity(value)
        with self.assertRaises(p.Refused): p.threshold(' 10%', 1000)

    def test_source_known_omitted_loaded_maps_are_zero_without_guessed_defaults(self):
        for key in ('kubeReserved', 'systemReserved', 'evictionHard', 'evictionSoft',
                    'evictionSoftGracePeriod', 'evictionMinimumReclaim'):
            self.config['kubeletconfig'].pop(key)
        answer = self.collect()
        self.assertEqual(answer['policy']['reservedMemoryBytes'], {'kubeReserved': 0, 'systemReserved': 0})
        self.assertEqual(answer['policy']['thresholds'], [])
        self.config.pop('kubeletconfig')
        with self.assertRaises(p.Refused): self.collect()

    def test_long_quantity_goldens_through_actual_caller_and_cli(self):
        # Independent integer goldens from positive Kubernetes Value() ceiling.
        # This does not execute Go or reuse the collector's conversion arithmetic.
        cases = [('1.00000000000000000000000000001', 2),
                 ('1.00000000000000000000000000001Gi', 1073741825),
                 ('1.'+'0'*31+'1', 2), ('1.'+'0'*31+'1Gi', 1073741825),
                 ('1.'+'0'*255+'1', 2), ('1.'+'0'*255+'1Gi', 1073741825),
                 ('1.00000000000000000000000000001e3', 1001),
                 ('0.'+'0'*40+'1', 1), ('0.'+'0'*40+'e30', 0)]
        for value, expected in cases:
            with self.subTest(quantity=value):
                self.config['kubeletconfig']['kubeReserved']['memory'] = value
                answer = self.collect()
                self.assertEqual(answer['status'], 'MEASURED')
                self.assertEqual(answer['policy']['reservedMemoryBytes']['kubeReserved'], expected)
                self.assertNotIn('RAW-', json.dumps(answer))

    def test_quantity_precision_is_independent_of_decimal_context(self):
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(p.quantity('1.00000000000000000000000000001Gi'), 1073741825)
            self.assertEqual(p.quantity('1024Mi'), 1073741824)
            self.assertEqual(p.quantity('0.00000000000000000000000000001'), 1)

    def test_unsupported_quantity_arithmetic_size_is_unmeasured(self):
        for value in ('1e1000000000', '1e-1000000000', '1.'+'0'*5000+'1'):
            self.config['kubeletconfig']['kubeReserved']['memory'] = value
            with self.assertRaises(p.Refused) as found:
                self.collect()
            self.assertEqual(found.exception.code, 'POLICY_UNSUPPORTED')
            self.assertEqual(found.exception.verdict, 'UNMEASURED')

    def test_usage_and_unrelated_status_refresh_are_positive(self):
        for fault in ('usage_refresh', 'status_refresh'):
            self.fixture['fault'] = fault
            self.assertEqual(self.collect()['status'], 'MEASURED')

    def test_census_resource_drift_refuses(self):
        for fault in ('census_uid', 'resource'):
            self.fixture['fault'] = fault
            with self.assertRaises(p.Refused) as found:
                self.collect()
            self.assertEqual(found.exception.code, 'CENSUS_CHANGED')

    def test_identity_policy_and_cgroup_incarnation_drift_refuse(self):
        for fault, code in [('node_uid', 'IDENTITY_CHANGED'), ('boot', 'IDENTITY_CHANGED'),
                            ('policy', 'POLICY_CHANGED'), ('start', 'IDENTITY_CHANGED')]:
            self.fixture['fault'] = fault
            with self.assertRaises(p.Refused) as found:
                self.collect()
            self.assertEqual(found.exception.code, code)

    def test_missing_duplicate_redacted_and_bad_memory_never_become_zero(self):
        original = copy.deepcopy(self.summary)
        variants = [lambda: self.summary['node'].update(systemContainers=[]),
                    lambda: self.summary['node']['systemContainers'].append(copy.deepcopy(self.summary['node']['systemContainers'][0])),
                    lambda: self.summary['node']['memory'].pop('availableBytes'),
                    lambda: self.summary['node']['memory'].update(workingSetBytes='<redacted>'),
                    lambda: self.summary['node']['memory'].update(availableBytes=2**64-1),
                    lambda: self.summary['node']['memory'].update(usageBytes=0)]
        for change in variants:
            change()
            with self.assertRaises(p.Refused):
                self.collect()
            self.summary.clear(); self.summary.update(copy.deepcopy(original))

    def test_unknown_version_policy_quantity_and_grace_are_unmeasured(self):
        original = copy.deepcopy(self.config)
        for change in [lambda: self.config['kubeletconfig'].update(cgroupsPerQOS=False),
                       lambda: self.config['kubeletconfig']['kubeReserved'].update(memory='unlimited'),
                       lambda: self.config['kubeletconfig']['evictionHard'].update({'newMemory.available': '1Gi'}),
                       lambda: self.config['kubeletconfig'].update(evictionSoftGracePeriod={})]:
            change()
            with self.assertRaises(p.Refused) as found:
                self.collect()
            self.assertEqual(found.exception.verdict, 'UNMEASURED')
            self.config.clear(); self.config.update(copy.deepcopy(original))
        changed = copy.deepcopy(self.node); changed['status']['nodeInfo']['kubeletVersion'] = 'v1.35.0'
        with self.assertRaises(p.Refused):
            p.node_identity(changed)

    def test_stale_future_and_missing_source_timestamps_refuse(self):
        for value in ('2020-01-01T00:00:00Z', '2099-01-01T00:00:00Z', None):
            self.summary['node']['memory']['time'] = value
            with self.assertRaises(p.Refused) as found:
                self.collect()
            self.assertEqual(found.exception.verdict, 'UNMEASURED')

    def test_scope_source_tool_private_file_and_foreign_context_are_bound(self):
        for key in ('sourceSha256', 'helperSha256'):
            old = self.scope[key]; self.scope[key] = '0'*64
            with self.assertRaises(p.Refused) as found:
                self.collect()
            self.assertEqual(found.exception.code, 'SOURCE_CHANGED'); self.assertFalse(self.log.exists())
            self.scope[key] = old
        old = self.scope['tools']['kubectl']['sha256']; self.scope['tools']['kubectl']['sha256'] = '0'*64
        with self.assertRaises(p.Refused): self.collect()
        self.assertFalse(self.log.exists()); self.scope['tools']['kubectl']['sha256'] = old
        self.scope['context'] = 'foreign-context'
        with self.assertRaises(p.Refused): self.collect()
        self.assertFalse(self.log.exists())
        self.scope['context'] = 'synthetic-context'; self.refresh(); self.scopefile.chmod(0o644)
        with self.assertRaises(p.Refused): p.collect(self.ref)

    def test_request_does_not_accept_endpoint_argv_or_context_override(self):
        for extra in ('argv', 'url', 'context'):
            request = {'version': 1, 'scope': self.ref, 'nonce': 'a'*64, extra: 'SYNTHETIC-SECRET'}
            result = subprocess.run([sys.executable, '-B', str(Path(p.__file__))], input=json.dumps(request).encode(),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads(result.stdout)['code'], 'REQUEST')
            self.assertNotIn(b'SYNTHETIC-SECRET', result.stdout+result.stderr)
            self.assertFalse(self.log.exists())

    def test_caller_rejects_forged_nonce_projection_and_extra_private_fields(self):
        for mutate in [lambda x: x.update(nonce='0'*64),
                       lambda x: x['samples'][0]['root'].update(usageBytes=99*Mi),
                       lambda x: x['policy'].update(secret='RAW-CONFIG-MUST-STAY-PRIVATE')]:
            def runner(argv, **kwargs):
                result = subprocess.run(argv, **kwargs); answer = json.loads(result.stdout); mutate(answer)
                return SimpleNamespace(returncode=0, stdout=json.dumps(answer).encode(), stderr=b'RAW-ERROR-SECRET')
            self.refresh()
            with self.assertRaises(p.Refused): p.collect(self.ref, runner=runner)

    def test_output_loss_api_errors_and_timeout_do_not_leak(self):
        for fault in ('lost_output', 'api_failure'):
            self.fixture['fault'] = fault
            self.refresh()
            request = {'version': 1, 'scope': self.ref, 'nonce': 'a'*64}
            result = subprocess.run([sys.executable, '-B', str(Path(p.__file__))], input=json.dumps(request).encode(),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads(result.stdout)['verdict'], 'UNMEASURED')
            self.assertNotIn(b'RAW-', result.stdout+result.stderr)
        with self.assertRaises(p.Refused) as found:
            p.collect(self.ref, runner=lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(a, 1, output=b'RAW-ERROR-SECRET')))
        self.assertEqual(found.exception.verdict, 'UNMEASURED')

    def test_original_deadline_checked_before_and_after_get(self):
        self.scope['until'] = time.time()-1; self.refresh()
        with self.assertRaises(p.Refused) as found: p.collect(self.ref)
        self.assertEqual(found.exception.code, 'DEADLINE'); self.assertFalse(self.log.exists())
        clock = SimpleNamespace(now=time.time()); clock.time = lambda: clock.now
        self.scope['until'] = clock.now+1; self.refresh(); calls = []
        def late(argv, **kwargs):
            calls.append(argv); clock.now += 2
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.node).encode(), stderr=b'')
        with self.assertRaises(p.Refused) as found:
            p.prove({'version': 1, 'scope': self.ref, 'nonce': 'a'*64}, runner=late, clock=clock)
        self.assertEqual(found.exception.code, 'DEADLINE'); self.assertEqual(len(calls), 1)

    def test_accepted_response_cap_and_missing_capsule_are_typed_refusals(self):
        def huge(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=b' '*(p.MAX_BYTES+1), stderr=b'RAW-ERROR-SECRET')
        with self.assertRaises(p.Refused) as found:
            p.prove({'version': 1, 'scope': self.ref, 'nonce': 'a'*64}, runner=huge)
        self.assertEqual(found.exception.code, 'API_UNAVAILABLE')
        self.scopefile.unlink()
        with self.assertRaises(p.Refused) as found: p.collect(self.ref)
        self.assertEqual(found.exception.verdict, 'UNMEASURED')


if __name__ == '__main__':
    unittest.main()
