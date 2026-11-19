"""Collector coverage and semantic controls; no application capacity claim."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import role_instances as r
import profile_provenance as p
import adapter as a
from contract import OWNER


def config(k=2, apis=2):
    services = {}
    for role, count in (('api', apis), ('evaluator', k), ('realtime', k)):
        for ordinal in range(count):
            service = role if ordinal == 0 else role + '-' + str(ordinal + 1)
            services[service] = {'command': ['node', 'deploy/multitenant/entrypoint.js', role], 'environment': {}}
            if role != 'api':
                services[service]['labels'] = {'org.nightscout.static-ownership.ordinal': str(ordinal),
                                               'org.nightscout.static-ownership.count': str(count)}
    return {'services': services}


def manifest(apis=2):
    return {'owner': 'a' * 32, 'project': 'ns-ordinal-control', 'imageId': 'sha256:' + 'b' * 64,
            'pair': {'core': 'c' * 40, 'deploy': 'd' * 40}, 'replicas': apis, 'diagnostics': p.selection('off')}


def rows(c, m):
    return [{'Id': 'physical-' + name, 'Image': m['imageId'], 'Config': {'Cmd': ['node', 'deploy/multitenant/entrypoint.js', r.instance(name)['role']],
             'Labels': {OWNER: m['owner'], 'com.docker.compose.project': m['project'],
                        'com.docker.compose.service': name, **spec.get('labels', {})}},
             'State': {'Running': True, 'StartedAt': '2026-11-17T00:00:00Z', 'Pid': 100 + i}}
            for i, (name, spec) in enumerate(c['services'].items())]


class Instances(unittest.TestCase):
    def test_actual_config_roster_k1_k2_n1_n2_and_wrong_ordinal_refusal(self):
        for k in (1, 2):
            for apis in (1, 2):
                c = config(k, apis); expected = r.roster(c, apis)
                self.assertEqual(len(expected), apis + k * 2)
                self.assertEqual([v['ordinal'] for v in expected.values() if v['role'] == 'evaluator'], list(range(k)))
                self.assertEqual(set(r.runtime(rows(c, manifest(apis)), expected, manifest(apis))), set(expected))
        good = config()
        for edit, code in ((lambda c: c['services'].pop('api'), 'ORDINAL_COVERAGE'),
                           (lambda c: c['services']['realtime-2']['labels'].update({'org.nightscout.static-ownership.ordinal': '0'}), 'DECLARED_ORDINAL'),
                           (lambda c: c['services']['api-2'].update(command=['node', 'realtime']), 'COMMAND_ROLE')):
            bad = copy.deepcopy(good); edit(bad)
            with self.assertRaisesRegex(RuntimeError, code): r.roster(bad, 2)
        self.assertEqual(len(r.roster(good, 2)), 6)

    def test_runtime_missing_duplicate_foreign_birth_and_ordinal_refuse_restored(self):
        c = config(); m = manifest(); expected = r.roster(c, 2); original = rows(c, m)
        bad_cases = [original[:-1], original + [original[-1]]]
        for field, value in (('com.docker.compose.service', 'realtime-3'), (OWNER, 'e' * 32),
                             ('org.nightscout.static-ownership.ordinal', '0')):
            bad = copy.deepcopy(original); bad[-1]['Config']['Labels'][field] = value; bad_cases.append(bad)
        for bad in bad_cases:
            with self.assertRaisesRegex(RuntimeError, 'M7_INSTANCE_'): r.runtime(bad, expected, m)
        bad = copy.deepcopy(original); bad[-1]['State']['Running'] = False
        with self.assertRaisesRegex(RuntimeError, 'RUNTIME_BIRTH'): r.runtime(bad, expected, m)
        self.assertEqual(len(r.runtime(original, expected, m)), 6)

    def test_static_runtime_requires_exact_topology(self):
        for k, apis in ((1, 1), (2, 2)):
            c = config(k, apis); m = {**manifest(apis), 'staticTopology': {'kind': 'static-hash-v1', 'workers': k}}
            expected = r.roster(c, apis); original = rows(c, m)
            self.assertEqual(set(r.runtime(original, expected, m)), set(expected))
            bad_manifest = {**m, 'staticTopology': {'kind': 'static-hash-v1', 'workers': k + 1}}
            with self.assertRaisesRegex(RuntimeError, 'M7_INSTANCE_RUNTIME_TOPOLOGY'):
                r.runtime(original, expected, bad_manifest)
            bad = copy.deepcopy(original); bad[-1]['Id'] = bad[-2]['Id']
            with self.assertRaisesRegex(RuntimeError, 'M7_INSTANCE_RUNTIME_IDENTITY'):
                r.runtime(bad, expected, m)
            self.assertEqual(set(r.runtime(original, expected, m)), set(expected))

    def test_mounted_assignment_does_not_require_docker_inspect_environment(self):
        for k, apis in ((1, 1), (2, 2)):
            c = config(k, apis); m = {**manifest(apis), 'staticTopology': {'kind': 'static-hash-v1', 'workers': k}}
            expected = r.roster(c, apis)
            with TemporaryDirectory() as tmp:
                state = Path(tmp)
                for service, item in expected.items():
                    if item['role'] == 'api': continue
                    value = {'count': k, 'ordinal': item['ordinal']}
                    if item['role'] == 'evaluator':
                        value['receivers'] = ['http://' + ('evaluator' if i == 0 else 'evaluator-' + str(i + 1)) + ':19913/' for i in range(k)]
                    field = 'NS_REALTIME_SLICE' if item['role'] == 'realtime' else 'NS_PGSTREAM_EVALUATOR_SLICE'
                    directory = state / service; directory.mkdir()
                    (directory / 'env.json').write_text(json.dumps({field: json.dumps(value)}))
                    c['services'][service]['volumes'] = [{'type': 'bind', 'source': str(directory), 'target': '/run/ns-config', 'read_only': True}]
                    r.assignment(item, json.loads((directory / 'env.json').read_text()), expected)
                values = rows(c, m)
                self.assertTrue(all(not row['Config'].get('Env') for row in values))
                self.assertEqual(set(r.runtime(values, expected, m)), set(expected))
                # Mounted-file validity and inspect identity do not prove process-loaded assignment.

    def test_one_worker_cannot_impersonate_static_roster_with_stale_or_omitted_peers(self):
        c = config(); m = {**manifest(), 'staticTopology': {'kind': 'static-hash-v1', 'workers': 2}}
        expected = r.roster(c, 2); original = rows(c, m)
        worker = next(i for i, row in enumerate(original) if row['Config']['Labels']['com.docker.compose.service'] == 'evaluator-2')
        omitted = original[:worker] + original[worker + 1:]
        with self.assertRaisesRegex(RuntimeError, 'M7_INSTANCE_RUNTIME_ROSTER'):
            r.runtime(omitted, expected, m)
        stale = copy.deepcopy(original)
        stale[worker]['Config']['Env'] = ['NS_PGSTREAM_EVALUATOR_SLICE=' + json.dumps({'count': 2, 'ordinal': 0,
            'receivers': ['http://evaluator:19913/', 'http://evaluator-2:19913/']})]
        with self.assertRaisesRegex(RuntimeError, 'M7_INSTANCE_DECLARED_ORDINAL'):
            r.runtime(stale, expected, m)
        self.assertEqual(set(r.runtime(original, expected, m)), set(expected))

    def test_attachment_uses_recorded_runtime_owner_and_retains_identity_fences(self):
        c = config(); original_manifest = manifest(); expected = r.roster(c, 2)
        original = rows(c, original_manifest)
        attached = {**original_manifest, 'owner': 'e' * 32, 'attached': True,
                    'runtimeOwnerLabels': [original_manifest['owner']]}
        self.assertEqual(len(r.runtime(original, expected, attached)), 6)
        for mutate, code in [
                (lambda row: row['Config']['Labels'].pop(OWNER), 'RUNTIME_IDENTITY'),
                (lambda row: row['Config']['Labels'].update({OWNER: 'f' * 32}), 'RUNTIME_IDENTITY'),
                (lambda row: row.update(Image='sha256:' + 'f' * 64), 'RUNTIME_IDENTITY'),
                (lambda row: row['State'].pop('StartedAt'), 'RUNTIME_BIRTH'),
                (lambda row: row['Config']['Labels'].update({'org.nightscout.static-ownership.ordinal': '0'}), 'DECLARED_ORDINAL')]:
            bad = copy.deepcopy(original);mutate(bad[-1])
            with self.assertRaisesRegex(RuntimeError, code): r.runtime(bad, expected, attached)
            self.assertEqual(len(r.runtime(original, expected, attached)), 6)
        for bad in ({**attached, 'runtimeOwnerLabels': []}, {**attached, 'attached': False}):
            with self.assertRaisesRegex(RuntimeError, 'RUNTIME_IDENTITY'): r.runtime(original, expected, bad)

    def test_missing_roster_guard_ablation_goes_red_then_restored(self):
        original = Path(r.__file__).read_text()
        broken = original.replace("    require(set(result) == set(expected), 'M7_INSTANCE_RUNTIME_ROSTER')", '    # CONTROL: omit completeness refusal')
        self.assertNotEqual(broken, original)
        scope = {'__file__': r.__file__}; exec(compile(broken, r.__file__, 'exec'), scope)
        c = config(); m = manifest(); expected = r.roster(c, 2); values = rows(c, m)[:-1]
        def criterion(runtime):
            try: runtime(values, expected, m)
            except RuntimeError: return
            raise AssertionError('MISSING_INSTANCE_MUST_REFUSE')
        criterion(r.runtime)
        with self.assertRaisesRegex(AssertionError, 'MISSING_INSTANCE_MUST_REFUSE'): criterion(scope['runtime'])
        criterion(r.runtime)

    def test_diagnostics_and_logs_cover_all_instances_duplicate_runtime_refuses(self):
        c = config(3, 2); chosen = p.selection('on'); p.select_environment(c, chosen)
        self.assertEqual(set(p.log_roles(c)), set(c['services']))
        observed = rows(c, manifest())
        for row in observed: row['Config']['Env'] = ['NS_M7_DIAGNOSTICS=1', 'NS_M7_DIAGNOSTICS_INTERVAL_MS=5000']
        p.runtime_environment(observed, chosen, c)
        with self.assertRaisesRegex(RuntimeError, 'ROSTER_MISMATCH'): p.runtime_environment(observed[:-1], chosen, c)
        with self.assertRaisesRegex(RuntimeError, 'ROSTER_MISMATCH'): p.runtime_environment(observed + observed[-1:], chosen, c)
        p.runtime_environment(observed, chosen, c)

    def test_effective_limits_missing_invalid_and_restored(self):
        row = {'Id': 'exact', 'HostConfig': {'NanoCpus': 500000000, 'Memory': 1048576}}
        class A:
            def command(self, argv):
                self.argv = argv; return '50000 100000\n1048576\n0\n'
        a = A(); good = r.effective_limits(a, row)
        self.assertEqual((good['millicpus'], good['memoryBytes'], good['swapBytes']), (500, 1048576, 0))
        self.assertEqual(a.argv[2], 'exact')
        with patch.object(a, 'command', return_value='max 0\nmax\n0'): self.assertEqual(r.effective_limits(a, row)['status'], 'UNMEASURED')
        self.assertEqual(r.effective_limits(a, row), good)

    def test_actual_snapshot_keeps_partial_counters_and_never_overwrites_duplicate(self):
        c = config(); m = {**manifest(), 'staticTopology': {'kind': 'static-hash-v1', 'workers': 2}}; original = rows(c, m)
        for row in original: row['Name'] = row['Id']
        stale_assignment = copy.deepcopy(original)
        stale_assignment[-1]['Config']['Env'] = ['NS_REALTIME_SLICE=' + json.dumps({'count': 2, 'ordinal': 0})]
        for mode, values in (('normal', original), ('missing', original[:-1]), ('duplicate', original + original[-1:]),
                             ('assignment', stale_assignment), ('topology', original)):
            with TemporaryDirectory() as tmp:
                root=Path(tmp); selected = copy.deepcopy(m)
                if mode == 'topology': selected['staticTopology']['workers'] = 1
                a.write(root/'owner.json',selected); a.write(root/'frozen.compose.json',c)
                def command(argv):
                    if argv[-1] == 'pid,comm,rss':return 'PID COMMAND RSS\n999999 node 20\n'
                    return 'usage_usec 100\n1024\nanon 512\n'
                with patch.object(a,'resources',return_value=values), patch.object(a,'command',side_effect=command), patch.object(a,'psql',return_value=''), patch.object(a,'memory_observation',return_value={'status':'UNMEASURED'}), patch.object(a,'compose',side_effect=RuntimeError('M7_OPTIONAL_TEST')):
                    a.phase_snapshot(root,root,'before')
                captured=a.document(root/'before-cgroups.json')
                self.assertEqual(captured['serviceCoverage']['status'],'MEASURED' if mode=='normal' else 'UNMEASURED')
                self.assertTrue((root/'before-pg-statements.tsv').is_file())
                self.assertEqual(captured['roles']['api-2']['cgroup'],'usage_usec 100\n1024\nanon 512\n')
                if mode=='duplicate':self.assertTrue(captured['roles']['realtime-2']['unavailable'])

    def test_shared_sql_role_is_mapped_once_never_split_by_process(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp); c = config(); expected = r.roster(c, 2)
            for service in expected:
                directory = state/service; directory.mkdir()
                (directory/'env.json').write_text(json.dumps({'PG':'postgres://synthetic:fixture@localhost/test'}))
                c['services'][service]['volumes'] = [{'type':'bind','source':str(directory),'target':'/run/ns-config','read_only':True}]
            value = r.sql_coverage(c, expected, state)
            self.assertEqual(value['sharedSqlRoles'], ['synthetic'])
            self.assertEqual(len(value['sqlRoleConsumers']['synthetic']), 6)
            self.assertEqual(value['processAttribution'], 'UNMEASURED')
            self.assertNotIn('fixture', json.dumps(value)); self.assertNotIn('localhost', json.dumps(value))
            (state/'api-2/env.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'IDENTITY_MISSING'): r.sql_coverage(c, expected, state)


if __name__ == '__main__': unittest.main()
