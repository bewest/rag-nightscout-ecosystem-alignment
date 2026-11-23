"""python3 -B -m unittest discover -s tools/mt-bench/kubernetes/connectors -p 'test_*.py'"""
import copy
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'workloads'))
import connectors  # noqa: E402
import profile as workload_profile  # noqa: E402


def roster(n):
    return [{'id': '3000%04x-3333-4333-8333-%012x' % (i, i), 'host': 't%d.example.test' % i, 'dataToken': 'tok%d' % i} for i in range(n)]


class Selection(unittest.TestCase):
    def test_share_takes_the_roster_tail_outside_the_ordinary_roster(self):
        pop = {'provisionedTenants': 20, 'ordinaryRosterTenants': 15, 'connectorShare': 0.25}
        chosen = connectors.select(roster(20), pop)
        self.assertEqual([r['host'] for r in chosen], ['t%d.example.test' % i for i in range(15, 20)])
        self.assertEqual([r['site'] for r in chosen], ['s0', 's1', 's2', 's3', 's4'])
        self.assertEqual(connectors.count(1000, 0.10), 100)
        self.assertEqual(connectors.select(roster(4), {'provisionedTenants': 4, 'ordinaryRosterTenants': 4}), [])

    def test_connector_tenants_that_also_receive_uploader_writes_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            connectors.validate({'provisionedTenants': 20, 'ordinaryRosterTenants': 16, 'connectorShare': 0.25})
        with self.assertRaisesRegex(ValueError, 'SHARE'):
            connectors.validate({'provisionedTenants': 20, 'ordinaryRosterTenants': 10, 'connectorShare': 1.5})

    def test_inputs_and_manifests(self):
        chosen = connectors.select(roster(8), {'provisionedTenants': 8, 'ordinaryRosterTenants': 6, 'connectorShare': 0.25})
        tokens = connectors.sites(chosen, token=iter(['a' * 32, 'b' * 32]).__next__)
        entry = connectors.entry_input(chosen, tokens)
        self.assertEqual(entry['tenants'][1], {'id': chosen[1]['id'], 'endpoint': 'http://nightscout-upstream:1337/s/s1', 'sourceCredential': 'b' * 32})
        self.assertEqual(entry['collections'], ['entries', 'treatments', 'devicestatus'])
        score = connectors.score_input(chosen, 123)
        self.assertEqual(score['tenants'][0]['token'], 'tok6')
        objs = connectors.manifests('lanev-vcpool', 'localhost:14100/app@sha256:' + '0' * 64, 123, {'nightscout.org/run-id': 'r1'})
        kinds = sorted((o['kind'], o['metadata']['name']) for o in objs)
        self.assertEqual(kinds, [('ConfigMap', 'connector-scripts'), ('Deployment', 'connector-score'), ('Deployment', 'nightscout-upstream'),
                                 ('NetworkPolicy', 'upstream-from-vcpool'), ('Service', 'nightscout-upstream')])
        policy = next(o for o in objs if o['kind'] == 'NetworkPolicy')
        self.assertEqual([f['podSelector']['matchLabels']['app.kubernetes.io/component'] for f in policy['spec']['ingress'][0]['from']], ['vcpool', 'operator'])
        self.assertTrue(all(o['metadata']['labels']['nightscout.org/run-id'] == 'r1' for o in objs))


class Profile(unittest.TestCase):
    def base(self):
        p = json.loads((HERE.parent / 'workloads' / 'small.json').read_text())
        p['population'].update(provisionedTenants=4, ordinaryRosterTenants=3)
        return p

    def test_profile_accepts_a_share_outside_the_ordinary_roster_and_describes_it(self):
        p = self.base(); p['population']['connectorShare'] = 0.25
        workload_profile.validate(p)
        self.assertEqual(workload_profile.describe(p)['connectorTenants'], 1)
        self.assertNotIn('connectorTenants', workload_profile.describe(self.base()))

    def test_profile_refuses_connectors_on_uploader_tenants(self):
        p = self.base(); p['population']['connectorShare'] = 0.5
        with self.assertRaisesRegex(ValueError, 'K8S_LOAD_CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            workload_profile.validate(p)


class LoopingGroup(unittest.TestCase):
    """looping-v2 covers every fixture tenant except the connector group, which receives no uploads."""
    def profile(self, **population):
        sys.path.insert(0, str(HERE.parent))
        import kube_adapter  # noqa: F401
        import plannable
        import populated_history as h
        base = {'version': 1, 'kind': 'k8s-m7-workload-profile', 'name': 'b', 'basis': 'x',
                'history': {'mode': 'synthetic-history-2d-v1', 'anchorUnixMs': 1},
                'phases': {'workSeconds': 7200, 'cleanupSeconds': 600, 'restart': False, 'reconnectBurstClients': 0},
                'workload': {'workloadMix': 'realistic-v1', 'loadSeconds': 1800, 'logicalPollingClients': 0, 'probeEveryMs': 300000},
                'population': {'hotFactor': 1, 'provisionedTenants': 1000, 'ordinaryRosterTenants': 1000}, 'capacityAcceptance': 'NOT_GRANTED'}
        p = plannable.profile(base, tenants=1000, history_mode=plannable.LOOPING_2D_V2)
        p['history'] = {'mode': 'synthetic-history-looping-2d-v2', 'anchorUnixMs': 1795000200000 - 1795000200000 % h.STEP_MS, 'seed': 7,
                        'cgmOnlyPercent': 10, 'cgmOnlyWithoutProfilePercent': 0, 'deepHistoryTenants': 0, 'deepHistoryDays': 3}
        p['population'].update(population)
        p['referencePins'] = {'core': 'a' * 40, 'deploy': 'b' * 40, 'bindingCommit': 'c' * 40}
        return p

    def test_connector_group_is_outside_the_looping_offer(self):
        workload_profile.validate(self.profile(), require_pins=False)
        p = self.profile(ordinaryRosterTenants=900, connectorShare=0.1)
        workload_profile.validate(p, require_pins=False)
        self.assertEqual(workload_profile.describe(p)['connectorTenants'], 100)
        with self.assertRaisesRegex(ValueError, 'LOOPING_OFFER_REQUIRES_FULL_FIXTURE_ROSTER'):
            workload_profile.validate(self.profile(ordinaryRosterTenants=900), require_pins=False)
        with self.assertRaisesRegex(ValueError, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            workload_profile.validate(self.profile(ordinaryRosterTenants=950, connectorShare=0.1), require_pins=False)


class Stage(unittest.TestCase):
    def test_start_creates_labelled_secrets_objects_and_runs_the_entry_job(self):
        import tempfile
        import stage
        calls = []
        def call(argv, data=None, read=True, timeout=None):
            calls.append((argv, data))
            if argv[:2] == ['get', 'deployment']:
                return b'1'
            if argv[:2] == ['get', 'job']:
                return b'1:'
            if argv[:2] == ['get', 'pods']:
                return json.dumps({'items': [{'spec': {'nodeName': 'node-b', 'volumes': [{'persistentVolumeClaim': {'claimName': 'primer-results'}}]},
                                              'status': {'phase': 'Running'}}]}).encode()
            return b''
        rows = [{'id': r['id'], 'host': r['host'], 'token': r['dataToken']} for r in roster(20)]
        c = {'runId': 'r1', 'namespace': 'lanev-vcpool', 'connectors': {'share': 0.25, 'ordinaryRosterTenants': 15,
                                                                       'image': 'localhost:14100/app@sha256:' + '0' * 64}}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            record = stage.start(call, c, rows, out, now=1795463000)
            self.assertEqual(record['tenants'], 5)
            self.assertEqual(oct((out / 'connector-score-input.private.json').stat().st_mode & 0o777), '0o600')
        verbs = [a[0][:2] for a in calls]
        self.assertEqual(verbs[:6], [['create', 'secret'], ['label', 'secret']] * 3)
        self.assertEqual([a[0][3] for a in calls if a[0][:2] == ['create', 'secret']], list(stage.SECRETS))
        entry = json.loads(next(d for a, d in calls if a[:4] == ['create', 'secret', 'generic', 'ns-connector-entry']))
        self.assertEqual([t['id'] for t in entry['tenants']], [r['id'] for r in rows[15:]])
        self.assertTrue(all(not a[0][0] == 'label' or a[0][-1] == 'nightscout.org/run-id=r1' for a in calls))
        self.assertIn(['patch', 'job', 'connector-entry', '--type=merge', '-p', '{"spec":{"suspend":false}}'], [a[0] for a in calls])
        applied = json.loads(next(d for a, d in calls if a[0] == 'apply'))
        self.assertEqual(len(applied['items']), 5)
        self.assertEqual(record['entryNode'], 'node-b')
        self.assertIn(['patch', 'job', 'connector-entry', '--type=merge', '-p',
                       '{"spec": {"template": {"spec": {"nodeSelector": {"kubernetes.io/hostname": "node-b"}}}}}'], [a[0] for a in calls])
        failing = lambda argv, data=None, read=True, timeout=None: (b'1' if argv[:2] == ['get', 'deployment'] else b':1' if argv[:2] == ['get', 'job']
                                                                    else b'{"items": []}' if argv[:2] == ['get', 'pods'] else b'')
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(RuntimeError, 'K8S_CONNECTOR_ENTRY_FAILED'):
            stage.start(failing, c, rows, Path(d), now=1795463000)
        # Every wait is a guarded read (`get`), never `wait` or `rollout`, which the read-only guard refuses.
        self.assertFalse(any(a[0][0] in ('wait', 'rollout') for a in calls))
        # Secret values never appear in argv.
        self.assertFalse(any('tok1' in ' '.join(a[0]) for a in calls))


class FailureEvidence(unittest.TestCase):
    """A connector stage failure keeps the entry Job, its Pods and logs and the namespace events before cleanup."""
    c = {'runId': 'r1', 'namespace': 'lanev-vcpool', 'connectors': {'share': 0.25, 'ordinaryRosterTenants': 15,
                                                                   'image': 'localhost:14100/app@sha256:' + '0' * 64}}

    def rows(self):
        return [{'id': r['id'], 'host': r['host'], 'token': r['dataToken']} for r in roster(20)]

    def fake(self, job):
        calls = []
        def call(argv, data=None, read=True, timeout=None):
            calls.append(argv)
            if argv[:2] == ['get', 'deployment']:
                return b'1'
            if argv[:2] == ['get', 'job'] and 'jsonpath' in argv[-1]:
                return job
            if argv[0] == 'logs':
                raise RuntimeError('K8S_OBSERVATION_LOST')  # e.g. a Pending Pod has no log yet
            if argv[:2] == ['get', 'pods'] and '-l' not in argv:
                return b'{"items": []}'
            return b'{"kind": "List", "items": []}'
        return call, calls

    def check(self, job, code):
        import tempfile
        import stage
        call, calls = self.fake(job)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            with self.assertRaisesRegex(RuntimeError, code):
                stage.start(call, self.c, self.rows(), out, now=1795463000)
            kept = out / 'connector-failure'
            receipt = json.loads((kept / 'receipt.json').read_text())
            self.assertEqual(receipt['code'], code)
            for name in ('connector-entry-job.json', 'connector-entry-pods.json', 'events.json', 'vcpool-pods.json', 'upstream-pods.json'):
                self.assertTrue((kept / name).is_file(), name)
                self.assertEqual(oct((kept / name).stat().st_mode & 0o777), '0o600')
            # A refused read is listed, never a stop.
            self.assertEqual(receipt['files']['connector-entry.log']['refused'], 'RuntimeError')
        # Secret objects are never read.
        self.assertFalse(any(a[:2] == ['get', 'secret'] or a[:2] == ['get', 'secrets'] for a in calls))

    def test_a_failed_entry_job_keeps_its_evidence(self):
        self.check(b':1', 'K8S_CONNECTOR_ENTRY_FAILED')

    def test_an_entry_job_that_never_finishes_is_a_timeout_and_keeps_its_evidence(self):
        import stage
        clock = type('Clock', (), {'t': 0.0, 'time': lambda self: self.t, 'sleep': lambda self, s: setattr(self, 't', self.t + 1000)})()
        with self.assertRaisesRegex(RuntimeError, 'K8S_CONNECTOR_ENTRY_TIMEOUT'):
            stage.until(lambda argv, read=True: b':', ['get'], lambda t: t.startswith('1:'), 600, 'K8S_CONNECTOR_ENTRY_FAILED',
                        clock=clock, failed=lambda t: t.endswith(':1'), timeout_code='K8S_CONNECTOR_ENTRY_TIMEOUT')


class ReaderEntry(unittest.TestCase):
    """Disposable storage: the entry runs in the fixture reader (the roster's root secrets never leave it);
    the load stage then creates only the upstream and scorer from the kept plan."""
    c = {'runId': 'r1', 'namespace': 'lanev-vcpool', 'connectors': {'share': 0.25, 'ordinaryRosterTenants': 6,
                                                                   'image': 'localhost:14100/app@sha256:' + '0' * 64}}

    def rows(self):
        return [{'id': r['id'], 'host': r['host'], 'token': r['dataToken']} for r in roster(8)]

    def test_entry_in_reader_keeps_a_private_plan_and_the_load_stage_skips_the_job(self):
        import subprocess
        import tempfile
        import stage
        seen = []
        def run(argv, input=None, capture_output=True, timeout=None):
            seen.append((argv, input))
            return subprocess.CompletedProcess(argv, 0, b'{"state":"connectors-entered","tenants":2,"counts":{}}\n', b'')
        with tempfile.TemporaryDirectory() as d:
            c = copy.deepcopy(self.c)
            path = stage.enter_in_reader(['kubectl', '-n', 'x'], 'fixture-reader-abc', self.rows(), c, Path(d) / 'connectors', 1e12,
                                         now=1795463000, run=run)
            self.assertEqual(oct(path.stat().st_mode & 0o777), '0o600')
            argv, data = seen[0]
            self.assertEqual(argv[3:8], ['exec', '-i', 'fixture-reader-abc', '-c', 'reader'])
            self.assertIn('NS_PRIMER_STATE=/results', argv)
            self.assertEqual([t['id'] for t in json.loads(data)['tenants']], [r['id'] for r in self.rows()[6:]])
            self.assertFalse(any('tok7' in a for a in argv), 'no credential in argv')
            receipt = json.loads((Path(d) / 'connectors' / 'connector-entry.json').read_text())
            self.assertEqual(receipt['result']['tenants'], 2)
            c['connectors']['planFile'] = str(path)
            calls = []
            def call(argv, data=None, read=True, timeout=None):
                calls.append(argv)
                return b'1' if argv[:2] == ['get', 'deployment'] else b''
            out = Path(d) / 'load'; out.mkdir()
            record = stage.start(call, c, self.rows(), out)
            self.assertEqual(record['entry'], 'fixture-reader')
            created = [a[3] for a in calls if a[:2] == ['create', 'secret']]
            self.assertEqual(created, ['ns-upstream-sites', 'ns-connector-score'])
            self.assertFalse(any(a[:2] == ['patch', 'job'] or a[:2] == ['get', 'job'] for a in calls))
            # The upstream serves the sites entered in the reader.
            plan = json.loads(path.read_text())
            self.assertEqual(sorted(plan['secrets']['ns-upstream-sites']), ['s0', 's1'])

    def test_a_failed_entry_in_the_reader_keeps_its_output_and_evidence(self):
        import subprocess
        import tempfile
        import stage
        def run(argv, input=None, capture_output=True, timeout=None):
            if 'exec' in argv:
                return subprocess.CompletedProcess(argv, 1, b'', b'{"error":"CONNECTOR_ENTRY_SUBJECT_CREATE_REFUSED","status":403}\n')
            return subprocess.CompletedProcess(argv, 0, b'{"items": []}', b'')
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(RuntimeError, 'K8S_CONNECTOR_ENTRY_FAILED'):
            try:
                stage.enter_in_reader(['kubectl'], 'fixture-reader-abc', self.rows(), copy.deepcopy(self.c), Path(d), 1e12, run=run)
            finally:
                receipt = json.loads((Path(d) / 'connector-entry.json').read_text())
                self.assertIn('CONNECTOR_ENTRY_SUBJECT_CREATE_REFUSED', receipt['stderr'])
                self.assertTrue((Path(d) / 'connector-failure' / 'events.json').is_file())
                self.assertFalse((Path(d) / 'connector-plan.private.json').exists())


if __name__ == '__main__':
    unittest.main()
