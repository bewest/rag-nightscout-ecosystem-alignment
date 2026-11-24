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
        up = next(o for o in objs if o['metadata']['name'] == 'nightscout-upstream' and o['kind'] == 'Deployment')
        env = {e['name']: e['value'] for e in up['spec']['template']['spec']['containers'][0]['env']}
        self.assertEqual(env['UPSTREAM_TIMING'], 'aid-v1')
        with self.assertRaisesRegex(ValueError, 'CONNECTOR_TIMING'):
            connectors.validate({'provisionedTenants': 8, 'ordinaryRosterTenants': 6, 'connectorShare': 0.25, 'connectorTiming': 'x'})
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
    """The connector group (roster tail) never overlaps the looping offer (an active prefix of the roster)."""
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
        # Candidate 2 (alignment 9ddced9e92) runs looping on an active prefix: a partial ordinary roster is valid.
        workload_profile.validate(self.profile(ordinaryRosterTenants=900), require_pins=False)
        with self.assertRaisesRegex(ValueError, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            workload_profile.validate(self.profile(ordinaryRosterTenants=950, connectorShare=0.1), require_pins=False)


    def test_points_share_one_connector_group_while_the_ordinary_prefix_can_grow(self):
        import tempfile
        import standard_case

        first = self.profile(ordinaryRosterTenants=400, connectorShare=0.1)
        first['workload']['pointId'] = 'first'
        second = self.profile(ordinaryRosterTenants=900, connectorShare=0.1)
        second['workload']['pointId'] = 'second'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'second.json'
            path.write_text(json.dumps(second))
            self.assertEqual(standard_case.point_profiles(first, [path]), [first, second])
            for change in ({'connectorShare': 0}, {'connectorShare': 0.05}, {'connectorTiming': 'stress-20-40'}):
                with self.subTest(change=change):
                    changed = copy.deepcopy(second)
                    changed['population'].update(change)
                    path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(standard_case.k.Refused, 'WORKLOAD_POINT_CONNECTORS_CHANGED'):
                        standard_case.point_profiles(first, [path])


class Stage(unittest.TestCase):
    def test_start_creates_labelled_secrets_objects_and_runs_the_entry_job(self):
        import tempfile
        import stage
        calls = []
        def call(argv, data=None, read=True, timeout=None):
            calls.append((argv, data))
            if argv[:3] == ['get', 'pods', '-l']:
                return b'score-pod:0'
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
                if argv[:3] == ['get', 'pods', '-l']:
                    return b'score-pod:0'
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

    def test_second_point_reuses_running_connectors_and_scores_from_its_own_start(self):
        import tempfile
        from unittest.mock import patch
        import stage

        secrets = set()
        mutations = []
        def call(argv, data=None, read=True):
            if not read:
                mutations.append(argv)
            if argv[:3] == ['get', 'pods', '-l']:
                return b'score-pod:0'
            if argv[:2] == ['logs', 'deployment/connector-score']:
                self.assertFalse(any(s.startswith('--since-time') for s in argv))
                return b'{"t":"start","at":20099000,"tenants":2}\n{"t":"sweep","at":23699000,"reads":6}\n'
            if argv[:2] == ['create', 'secret']:
                if argv[3] in secrets:
                    raise RuntimeError('AlreadyExists: ' + argv[3])
                secrets.add(argv[3])
            return b'1' if argv[:2] == ['get', 'deployment'] else b''

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            c = copy.deepcopy(self.c)
            path = root / 'plan.json'
            path.write_text(json.dumps(stage.plan(c, self.rows(), now=20000)))
            c['connectors']['planFile'] = str(path)
            first, second = root/'first', root/'second'
            first.mkdir()
            second.mkdir()
            with patch.object(stage.time, 'time', return_value=20100):
                initial = stage.start(call, c, self.rows(), first)
            first_mutations = list(mutations)
            c['connectors']['previousEntryMs'] = initial['enteredAt']
            with patch.object(stage.time, 'time', return_value=22500):
                continued = stage.start(call, c, self.rows(), second)
            self.assertEqual(mutations, first_mutations)
            self.assertEqual(continued['enteredAt'], initial['enteredAt'])
            self.assertEqual(continued['scoreFromMs'], 22500000)
            self.assertEqual(continued['historyStartMs'], initial['historyStartMs'])
            # With no observations the independent point must miss its eligible live records.
            scored = stage.collect(call, c, second, until=continued['scoreFromMs'] + 1200000)
            self.assertEqual(scored['window']['from'], continued['scoreFromMs'])
            self.assertEqual(scored['backfill']['scored'], 0)
            self.assertGreater(scored['live']['scored'], 0)
            self.assertEqual(scored['misses'], scored['live']['scored'])
            def rolled_log(argv, **kw):
                if argv[:2] == ['logs', 'deployment/connector-score']:
                    return b'{"t":"sweep","at":23699000,"reads":6}\n'
                return call(argv, **kw)
            partial = stage.collect(rolled_log, c, second, until=23700000)
            self.assertEqual(partial['verdict'], 'UNMEASURED')
            self.assertEqual(partial['code'], 'K8S_CONNECTOR_SCORE_LOG_INCOMPLETE')

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


class ProbeRoster(unittest.TestCase):
    """The probe and the ordinary driver never write into a connector tenant (by tenant id)."""
    def setUp(self):
        sys.path.insert(0, str(HERE.parent))
        import kube_adapter  # noqa: F401
        import workload_runtime
        self.w = workload_runtime

    def need(self, value, code):
        if not value:
            raise RuntimeError(code)

    def c(self, **extra):
        return {'tenants': 8, 'ordinaryRosterTenants': 6, 'workload': {},
                'connectors': {'share': 0.25, 'ordinaryRosterTenants': 6, 'image': 'x', **extra}}

    def test_probe_roster_excludes_the_connector_group(self):
        rows = [{'id': r['id'], 'host': r['host'], 'token': r['dataToken']} for r in roster(8)]
        viewers = self.w.viewer_roster(self.c(), rows, self.need)
        self.assertEqual([r['id'] for r in viewers], [r['id'] for r in rows[:6]])
        self.w.check_probe_roster(self.c(), viewers, rows, self.need)
        # Red control: the whole roster (the pre-fix probe input) carries the connector group and is refused.
        with self.assertRaisesRegex(RuntimeError, 'CONNECTOR_TENANT_IN_PROBE_ROSTER'):
            self.w.check_probe_roster(self.c(), rows, rows, self.need)
        self.assertEqual(self.w.viewer_roster({'tenants': 8, 'workload': {}}, rows, self.need), rows)

    def test_looping_prefix_is_host_ordered_and_the_group_is_its_complement(self):
        # Roster order differs from host order, as a primer may return it.
        rows = [{'id': r['id'], 'host': 'h%d.example.test' % ((i * 5) % 8), 'token': 't'} for i, r in enumerate(roster(8))]
        c = self.c(order='host'); c['workload'] = {'driverShape': 'looping-v2'}
        ordinary = {r['id'] for r in self.w.ordinary_roster(c, rows, self.need)}
        ids = self.w.connector_ids(c, rows)
        self.assertEqual(len(ids), 2)
        self.assertFalse(ids & ordinary)
        self.w.check_probe_roster(c, self.w.viewer_roster(c, rows, self.need), rows, self.need)
        # Red control: roster-order selection under a host-ordered prefix overlaps and is refused.
        c['connectors']['order'] = 'roster'
        with self.assertRaisesRegex(RuntimeError, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES'):
            self.w.check_probe_roster(c, [], rows, self.need)


class OracleScope(unittest.TestCase):
    """The write-count oracle counts probe and k6 writes over the probe roster: the connector group is vcpool's."""
    def setUp(self):
        sys.path.insert(0, str(HERE.parent))
        import kube_adapter  # noqa: F401
        import workload_runtime
        import discovery_counts
        self.w, self.d = workload_runtime, discovery_counts

    def need(self, value, code):
        if not value:
            raise RuntimeError(code)

    def ledger(self, roster_ids, d, runid='r1'):
        rows = {t: {'attempts': 1, 'accepted': 1, 'uncertain': 0, 'refused': 0, 'pending': 0} for t in roster_ids}
        (d / 'probe-accounting.json').write_text(json.dumps({'version': 2, 'kind': 'm7-discovery-probe-accounting', 'runId': runid,
            'roster': list(roster_ids), 'admissionsClosed': True, 'attempts': len(rows), 'byTenant': rows}))

    def test_scope_is_the_probe_roster_and_a_short_ledger_still_refuses(self):
        import tempfile
        from types import SimpleNamespace
        rows = [{'id': r['id'], 'host': r['host'], 'token': 't'} for r in roster(8)]
        c = {'tenants': 8, 'ordinaryRosterTenants': 6, 'workload': {}, 'connectors': {'share': 0.25, 'ordinaryRosterTenants': 6, 'image': 'x'}}
        scope = self.w.oracle_scope(c, rows, {}, True, self.need)
        probe = self.w.viewer_roster(c, rows, self.need)
        self.assertEqual([r['id'] for r in scope], [r['id'] for r in probe])
        self.assertEqual(self.w.oracle_scope(c, rows, {}, False, self.need), rows)
        with self.assertRaisesRegex(RuntimeError, 'CONNECTOR_TENANT_RECEIVED_RUN_WRITES'):
            self.w.oracle_scope(c, rows, {rows[7]['id']: {'entries': 1}}, True, self.need)
        a = SimpleNamespace(document=lambda f: json.loads(Path(f).read_text()))
        expected = {r['id'] for r in scope}
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.ledger([r['id'] for r in probe], d)
            self.d.probe_metadata(a, d, 'r1', expected)
            # Before the fix the oracle took the full roster: the probe's ledger (without the group) refused.
            with self.assertRaisesRegex(Exception, 'M7_PROBE_COUNTS_ROSTER'):
                self.d.probe_metadata(a, d, 'r1', {r['id'] for r in rows})
            # Red control: a ledger that omits a probe tenant still refuses.
            self.ledger([r['id'] for r in probe[1:]], d)
            with self.assertRaisesRegex(Exception, 'M7_PROBE_COUNTS_ROSTER'):
                self.d.probe_metadata(a, d, 'r1', expected)


if __name__ == '__main__':
    unittest.main()
