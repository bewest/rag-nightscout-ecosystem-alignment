"""Synthetic custody/observation joins and real concurrent finite children.

No cluster mutation, HTTP application qualification or capacity acceptance.
"""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_adapter import fixture, iso, A, B, k, execute as e
import matrix as m
ORIGINAL_JOIN = m.joined_point


class Matrix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.entries = []
        for i in range(2):
            c, inv, render, client = fixture()
            c.update(runId='synthetic-' + str(i), namespace='synthetic-' + str(i),
                     baseUrl='http://127.0.0.1:' + str(18080 + i), tenants=2,
                     tenantsFile=str(self.root / 'tenants.json'),
                     workload={'loadSeconds': 1, 'offeredRps': 1, 'logicalPollingClients': 2,
                               'probeEveryMs': 1000, 'hotFactor': 3})
            # Use the inherited synthetic API replies to construct exact
            # observation shape; only run/context/namespace custody differs.
            objects = k.validate(*fixture()[:3])
            original, _, _, replies = fixture()
            baseline = k.observe(original, objects, replies)
            baseline.update(runId=c['runId'], pins=c['pins'], driver=c['driver'], observer=c['observer'])
            baseline['namespace'].update(name=c['namespace'], uid='namespace-' + str(i))
            d = self.root / str(i)
            d.mkdir()
            k.write(d / 'run.json', c)
            k.write(d / 'qualification.json', {'verdict': 'OBSERVED_COMMISSIONING', 'pins': c['pins']})
            self.entries.append((d, c, objects, baseline))
        k.write(self.root / 'tenants.json', [{'id': A, 'token': 'synthetic-a', 'host': 'a.test'},
                                            {'id': B, 'token': 'synthetic-b', 'host': 'b.test'}])
        self.value = {'version': 1, 'fixtures': [str(e[0]) for e in self.entries],
                      'aggregateCeiling': {'millicpus': 10000, 'memoryBytes': 20 * 1024**3,
                                           'ephemeralBytes': 20 * 1024**3}}
        pre = self.root / 'preflight.json'
        k.write(pre, {'offline': 'PASS', 'commissioning': 'PREFLIGHT_ONLY'})
        self.a = {'version': 1, 'status': 'RELEASED', 'existingCapacityOnly': True,
                  'context': self.entries[0][1]['context'], 'workUntil': iso(time.time() + 180),
                  'cleanupUntil': iso(time.time() + 360), 'preflight': {'path': str(pre), 'sha256': k.digest(pre)},
                  'fixtures': [{'runId': c['runId'], 'namespace': c['namespace'],
                                'namespaceUid': b['namespace']['uid'], 'runSha256': k.digest(d / 'run.json')}
                               for d, c, _, b in self.entries],
                  'nodeCeilings': {'synthetic-node': copy.deepcopy(self.value['aggregateCeiling'])},
                  'actorCeilings': {host: {'millicpus': 10000, 'memoryBytes': 20 * 1024**3}
                                    for host in ('synthetic-driver', 'synthetic-observer')}}
        self.release()

    def release(self):
        path = self.root / 'allocation.json'
        k.write(path, self.a)
        self.value.update(allocation=str(path), allocationSha256=k.digest(path))

    def test_allocation_identity_headroom_deadline_controls(self):
        criterion = lambda: m.allocation(self.value, self.entries)
        criterion()
        changes = [('MATRIX_ALLOCATION_IDENTITY_CHANGED', lambda a: a['fixtures'][0].update(namespaceUid='foreign')),
                   ('MATRIX_NODE_HEADROOM_EXCEEDED', lambda a: a['nodeCeilings']['synthetic-node'].update(memoryBytes=1)),
                   ('MATRIX_ACTOR_HEADROOM_EXCEEDED', lambda a: a['actorCeilings']['synthetic-driver'].update(millicpus=1)),
                   ('MATRIX_ALLOCATION_DEADLINE', lambda a: a.update(workUntil=iso(time.time() - 1))),
                   ('MATRIX_CONTEXT_CHANGED', lambda a: a.update(context='foreign-context')),
                   ('MATRIX_FIXTURE_DEADLINE_EXCEEDS_ALLOCATION', lambda a: a.update(workUntil=iso(time.time() + 1)))]
        for code, change in changes:
            original = copy.deepcopy(self.a)
            change(self.a)
            self.release()
            with self.assertRaisesRegex(k.Refused, code):
                criterion()
            self.a = original
            self.release()
            criterion()
            print('RED_RESTORED', 'K8S_' + code)
        path = Path(self.a['preflight']['path'])
        before = path.read_bytes()
        path.write_bytes(before + b'\n')
        with self.assertRaisesRegex(k.Refused, 'MATRIX_PREFLIGHT_CHANGED'):
            criterion()
        path.write_bytes(before)
        criterion()
        print('RED_RESTORED K8S_MATRIX_PREFLIGHT_CHANGED')

    def test_counts_init_and_sidecar_and_missing_workload(self):
        a, totals = m.allocation(self.value, self.entries)
        node = totals['nodes']['synthetic-node']
        self.assertEqual(node['millicpus'], 4000)
        extra = copy.deepcopy(self.entries[0][2]['StatefulSet/cohort']['spec']['template']['spec']['containers'][0])
        extra.update(name='synthetic-init', restartPolicy='Always')
        spec = self.entries[0][2]['StatefulSet/cohort']['spec']['template']['spec']
        spec['initContainers'] = [extra]
        _, added = m.allocation(self.value, self.entries)
        self.assertEqual(added['nodes']['synthetic-node']['millicpus'], 4500)
        del spec['initContainers']
        baseline = self.entries[0][3]
        saved = baseline['pods'].pop('postgres-0')
        with self.assertRaisesRegex(k.Refused, 'MATRIX_WORKLOAD_CENSUS'):
            m.allocation(self.value, self.entries)
        baseline['pods']['postgres-0'] = saved
        m.allocation(self.value, self.entries)
        print('RED_RESTORED K8S_MATRIX_WORKLOAD_CENSUS')

    def test_statefulset_replicas_each_take_one_pod_budget(self):
        _, _, objects, baseline = self.entries[0]
        pod = next(p for p in baseline['pods'].values() if p['workload'] == 'StatefulSet/cohort')
        _, one = m.allocation(self.value, self.entries)
        baseline['pods']['cohort-extra'] = dict(copy.deepcopy(pod), name='cohort-extra')
        # A second Pod of a one-replica workload is still refused.
        with self.assertRaisesRegex(k.Refused, 'MATRIX_WORKLOAD_CENSUS'):
            m.allocation(self.value, self.entries)
        objects['StatefulSet/cohort']['spec']['replicas'] = 2
        _, two = m.allocation(self.value, self.entries)
        spec = k.template(objects['StatefulSet/cohort'])['spec']
        per_pod = k.resource_budget.pod_budget(spec, k.resource_accounting(self.a), k.need)['millicpus']
        self.assertEqual(two['nodes']['synthetic-node']['millicpus'] - one['nodes']['synthetic-node']['millicpus'], per_pod)
        baseline['pods']['cohort-third'] = dict(copy.deepcopy(pod), name='cohort-third')
        with self.assertRaisesRegex(k.Refused, 'MATRIX_WORKLOAD_CENSUS'):
            m.allocation(self.value, self.entries)

    def test_suspended_job_uses_no_node_budget_until_it_runs(self):
        _, _, objects, baseline = self.entries[0]
        _, initial = m.allocation(self.value, self.entries)
        workload = 'Job/primer'
        template = objects['StatefulSet/cohort']['spec']['template']
        objects[workload] = {'kind': 'Job', 'spec': {'suspend': True, 'template': template}}
        baseline['objects'][workload] = {'uid': 'fixture-primer'}
        self.assertEqual(m.allocation(self.value, self.entries)[1], initial)
        baseline['objects'][workload]['suspend'] = False
        with self.assertRaisesRegex(k.Refused, 'MATRIX_WORKLOAD_CENSUS'):
            m.allocation(self.value, self.entries)
        baseline['pods']['primer-1'] = {'name': 'primer-1', 'workload': workload, 'nodeName': 'synthetic-node'}
        _, running = m.allocation(self.value, self.entries)
        self.assertGreater(running['nodes']['synthetic-node']['millicpus'], initial['nodes']['synthetic-node']['millicpus'])

    def test_scheduler_reports_actor_requests_with_optional_host_ceilings(self):
        _, expected = m.allocation(self.value, self.entries)
        self.a['placementMode'] = 'scheduler'
        ceilings = self.a.pop('actorCeilings')
        self.release()
        self.assertEqual(m.allocation(self.value, self.entries)[1], expected)
        self.a['actorCeilings'] = ceilings
        ceilings['synthetic-driver']['millicpus'] = 1
        self.release()
        with self.assertRaisesRegex(k.Refused, 'MATRIX_ACTOR_HEADROOM_EXCEEDED'):
            m.allocation(self.value, self.entries)

    def test_phase_limits_match_node_and_aggregate_ceilings(self):
        # CPU peaks with a running sidecar and the later init, memory with
        # the app and both sidecars, disk in the first init before either.
        _, _, objects, _ = self.entries[0]
        spec = k.template(objects['StatefulSet/postgres'])['spec']
        def limits(mcpu, mib, disk):
            return {'cpu': str(mcpu) + 'm', 'memory': str(mib) + 'Mi',
                    'ephemeral-storage': str(disk) + 'Mi'}
        def init(name, resources, persistent=False):
            return {'name': name, 'resources': {'limits': resources},
                    **({'restartPolicy': 'Always'} if persistent else {})}
        spec['containers'][0]['resources']['limits'] = limits(100, 700, 10)
        spec['initContainers'] = [init('early', limits(500, 32, 900)),
                                  init('side-one', limits(200, 250, 100), True),
                                  init('later', limits(700, 64, 400)),
                                  init('side-two', limits(150, 200, 80), True)]
        spec['overhead'] = limits(10, 12, 30)
        # The other seven containers each request a 500m/256Mi/128Mi limit.
        expected = {'millicpus': 4410, 'memoryBytes': (7 * 256 + 1162) * 2**20,
                    'ephemeralBytes': (7 * 128 + 930) * 2**20}
        self.a['nodeCeilings']['synthetic-node'] = expected.copy()
        self.release()
        def load(directory):
            return next((d, c, o) for d, c, o, _ in self.entries if str(d) == directory)
        _, usage = m.allocation(self.value, self.entries)
        self.assertEqual(usage['nodes']['synthetic-node'], expected)
        with patch.object(k, 'load', side_effect=load):
            aggregate = expected.copy()
            for actor in usage['nativeActors'].values():
                for dim, amount in actor.items():
                    aggregate[dim] += amount
            self.value['aggregateCeiling'] = aggregate.copy()
            self.assertEqual(e.matrix_plan(self.value)['conservativeAggregateLimits'], aggregate)
            for dim in expected:
                self.a['nodeCeilings']['synthetic-node'][dim] -= 1
                self.release()
                with self.assertRaisesRegex(k.Refused, 'MATRIX_NODE_HEADROOM_EXCEEDED'):
                    m.allocation(self.value, self.entries)
                self.a['nodeCeilings']['synthetic-node'][dim] += 1
                self.release()
                self.assertEqual(m.allocation(self.value, self.entries)[1]['nodes']['synthetic-node'], expected)
                self.value['aggregateCeiling'][dim] -= 1
                with self.assertRaisesRegex(k.Refused, 'AGGREGATE_HEADROOM_EXCEEDED'):
                    e.matrix_plan(self.value)
                self.value['aggregateCeiling'][dim] += 1
                self.assertEqual(e.matrix_plan(self.value)['conservativeAggregateLimits'], aggregate)

    def test_setup_marker_cannot_establish_ordinary_load(self):
        log = self.root / 'k6.log'
        c = self.entries[0][1]
        def marker(name):
            event = json.dumps({'event': name, 'atMs': 11000})
            log.write_text('level=info msg=' + json.dumps(event) + ' source=console\n')
        marker('scenario-first-iteration')
        self.assertEqual(e.ordinary_load_window(c, log, 10, 15), (11, 12))
        marker('jwt-setup-start')
        with self.assertRaisesRegex(k.Refused, 'SCENARIO_DEMAND_UNMEASURED'):
            e.ordinary_load_window(c, log, 10, 15)
        marker('scenario-first-iteration')
        self.assertEqual(e.ordinary_load_window(c, log, 10, 15), (11, 12))
        print('RED_RESTORED K8S_SCENARIO_DEMAND_UNMEASURED')

    def test_distinct_point_markers_and_refused_point_scope(self):
        c = self.entries[0][1]
        first = e.stage_runid(c, 'load')
        c['workload']['pointId'] = 'sockets-16'
        second = e.stage_runid(c, 'load')
        self.assertNotEqual(first, second)
        c['workload']['pointId'] = '../foreign'
        with self.assertRaisesRegex(k.Refused, 'WORKLOAD_POINT_ID'):
            e.stage_runid(c, 'load')
        c['workload']['pointId'] = 'sockets-16'
        self.assertEqual(e.stage_runid(c, 'load'), second)
        print('RED_RESTORED K8S_WORKLOAD_POINT_ID')

    def test_original_http_and_offered_work_join_controls(self):
        import http_accounting
        out = self.root / 'functional';out.mkdir()
        metrics = {name: {'count': value} for name, value in {
            'scenario_request_attempts': 7, 'scenario_http_responses': 7,
            'scenario_transport_failures': 0, 'http_reqs': 7, 'dropped_iterations': 0}.items()}
        for shape in http_accounting.SHAPES:
            for key in ('m7_http_attempts{http_shape:' + shape + '}',
                        'm7_http_completed{http_shape:' + shape + '}',
                        'm7_http_completed{http_shape:' + shape + ',status:200}',
                        'm7_http_completed{http_shape:' + shape + ',category:http_expected}'):
                metrics[key] = {'count': 1}
            if shape.startswith('w_'):
                metrics['m7_http_write_outcome{http_shape:' + shape + ',outcome:accepted}'] = {'count': 1}
        def check(value):
            k.write(out / 'k6-summary.json', {'metrics': value})
            return e.load_checks(out)
        self.assertEqual(check(metrics)['http']['httpVerdict'], 'PASS')
        cases = []
        missing = {key: value for key, value in metrics.items() if 'http_shape:r_status' not in key}
        cases.append(('SCENARIO_SHAPE_UNMEASURED', missing))
        refused = copy.deepcopy(metrics)
        refused['m7_http_completed{http_shape:r_sgv,status:200}']['count'] = 0
        refused['m7_http_completed{http_shape:r_sgv,status:401}'] = {'count': 1}
        refused['m7_http_completed{http_shape:r_sgv,category:http_expected}']['count'] = 0
        refused['m7_http_completed{http_shape:r_sgv,category:http_refused}'] = {'count': 1}
        cases.append(('SCENARIO_HTTP_FAILED', refused))
        dropped = copy.deepcopy(metrics);dropped['dropped_iterations']['count'] = 1
        self.assertEqual(check(dropped)['http']['droppedIterations'], 1)  # drops are a figure
        self.assertEqual(check(dropped)['http']['httpVerdict'], 'PASS')
        missing_counter = copy.deepcopy(metrics);del missing_counter['http_reqs']
        cases.append(('SCENARIO_HTTP_FAILED', missing_counter))
        for code, broken in cases:
            with self.assertRaisesRegex(k.Refused, code):check(broken)
            self.assertTrue((out / 'load-functional.json').is_file())
            self.assertEqual(check(metrics)['http']['httpVerdict'], 'PASS')
            print('RED_RESTORED K8S_' + code)

    def point(self, d, c, baseline, *, start=10, end=20):
        out = d / 'load'
        out.mkdir(exist_ok=True)
        window = {'startedAt': start - 1, 'endedAt': end + 1, 'loadStartedAt': start, 'loadEndedAt': end,
                  'pins': c['pins'], 'context': c['context'], 'namespaceUid': baseline['namespace']['uid'],
                  'runId': c['runId'] + '-load'}
        result = {'verdict': 'OBSERVED', 'pins': c['pins'], 'clinical': {'verdict': 'PASS'}, 'frames': {'verdict': 'PASS'},
                  'evaluatorProgress': {'verdict': 'PASS'}, 'storedWrites': {'verdict': 'GREEN', 'uncertain': 0},
                  'loadFunctionalChecks': {'http': {'httpVerdict': 'PASS'},
                                           'settingsFingerprint': {'verdict': 'PASS'}}}
        probe = {'viewerBindings': [{'socket': 0, 'tenant': A}, {'socket': 1, 'tenant': B}],
                 'kubernetesFrames': {'overflow': False, 'rows': [
                     {'socket': i, 'tenant': tenant, 'ids': [], 'at': (start + .01) * 1000}
                     for i, tenant in enumerate((A, B))]}}
        for name, value in [('window', window), ('result', result), ('probe', probe)]:
            k.write(out / (name + '.json'), value)
        return ORIGINAL_JOIN(d, c, baseline, baseline)

    def test_existing_point_join_retains_realistic_selector_and_sparse_clients(self):
        d, c, _, baseline = self.entries[0]
        legacy = self.point(d, c, baseline)
        self.assertEqual(legacy['activity']['offeredRps'], 1)
        del c['workload']['offeredRps']
        c['workload'].update(workloadMix='realistic-v1', workloadScale=2, hotFactor=1, logicalPollingClients=1)
        path = d / 'load/probe.json'
        probe = k.document(path)
        probe['viewerBindings'] = probe['viewerBindings'][:1]
        probe['kubernetesFrames']['rows'] = probe['kubernetesFrames']['rows'][:1]
        k.write(path, probe)
        value = m.joined_point(d, c, baseline, baseline)
        self.assertNotIn('offeredRps', value['activity'])
        self.assertEqual(value['activity']['workloadMix'], 'realistic-v1')
        self.assertEqual(value['activity']['workloadScale'], 2)
        self.assertEqual(value['clientsByTenant'], {A: 1, B: 0})
        probe['kubernetesFrames']['rows'][0]['tenant'] = B
        k.write(path, probe)
        with self.assertRaisesRegex(k.Refused, 'MATRIX_FRAME_BINDING_CHANGED'):
            m.joined_point(d, c, baseline, baseline)
        probe['kubernetesFrames']['rows'][0]['tenant'] = A
        k.write(path, probe)
        self.assertEqual(m.joined_point(d, c, baseline, baseline)['activity'], value['activity'])
        print('RED_RESTORED K8S_MATRIX_FRAME_BINDING_CHANGED realistic sparse point')

    def test_overlap_missing_client_source_oracle_uid_controls(self):
        points = [self.point(d, c, b) for d, c, _, b in self.entries]
        self.assertGreater(m.overlap(points)['seconds'], 0)
        changed = copy.deepcopy(points)
        changed[1]['loadStartedAt'] = 30
        with self.assertRaisesRegex(k.Refused, 'MATRIX_NO_LOAD_OVERLAP'):
            m.overlap(changed)
        changed = copy.deepcopy(points)
        changed[1]['frames'].pop()
        with self.assertRaisesRegex(k.Refused, 'MATRIX_OVERLAP_FRAME_UNMEASURED'):
            m.overlap(changed)
        m.overlap(points)
        d, c, _, b = self.entries[0]
        for name, code, mutate in [
            ('window', 'MATRIX_RESULT_SOURCE_CHANGED', lambda v: v.update(namespaceUid='foreign')),
            ('result', 'MATRIX_ORACLE_UNMEASURED', lambda v: v['clinical'].update(verdict='UNMEASURED')),
            ('window', 'MATRIX_LOAD_WINDOW_UNMEASURED', lambda v: v.update(loadStartedAt=None)),
            ('probe', 'MATRIX_FRAME_BINDING_CHANGED', lambda v: v['kubernetesFrames']['rows'][0].update(tenant=B))]:
            path = d / 'load' / (name + '.json')
            original = k.document(path)
            broken = copy.deepcopy(original)
            mutate(broken)
            k.write(path, broken)
            with self.assertRaisesRegex(k.Refused, code):
                m.joined_point(d, c, b, b)
            k.write(path, original)
            m.joined_point(d, c, b, b)
            print('RED_RESTORED K8S_' + code)
        print('RED_RESTORED K8S_MATRIX_NO_LOAD_OVERLAP')
        print('RED_RESTORED K8S_MATRIX_OVERLAP_FRAME_UNMEASURED')

    def test_source_and_port_collision_controls(self):
        def load(path):
            return next((d, c, o) for d, c, o, _ in self.entries if str(d) == path)
        with patch.object(k, 'load', side_effect=load):
            e.matrix_plan(self.value)
            pins = self.entries[1][1]['pins']
            original = pins['instrument']
            pins['instrument'] = 'foreign'
            e.matrix_plan(self.value)  # instrument identity is recorded, not compared
            pins['instrument'] = original
            original = pins['appImageId']
            pins['appImageId'] = 'foreign'
            with self.assertRaisesRegex(k.Refused, 'MATRIX_MIXED_IMAGE'):
                e.matrix_plan(self.value)
            pins['appImageId'] = original
            e.matrix_plan(self.value)
            print('RED_RESTORED K8S_MATRIX_MIXED_IMAGE appImageId')
            c = self.entries[1][1]
            original = c['baseUrl']
            c['baseUrl'] = self.entries[0][1]['baseUrl'] + '/'
            with self.assertRaisesRegex(k.Refused, 'FIXTURE_FANOUT_COLLISION'):
                e.matrix_plan(self.value)
            c['baseUrl'] = original
            e.matrix_plan(self.value)
            print('RED_RESTORED K8S_FIXTURE_FANOUT_COLLISION canonical loopback port')

    def run_synthetic(self, mode='pass'):
        def load(path):
            return next((d, c, o) for d, c, o, _ in self.entries if str(d) == path)
        commands = []
        for i, (d, c, objects, baseline) in enumerate(self.entries):
            # Independent real children leave timing and completion evidence.
            code = "import pathlib,time,json; p=pathlib.Path(%r); a=time.time(); time.sleep(.15); p.write_text(json.dumps({'start':a,'end':time.time()}))" % str(d / 'child.json')
            if mode == 'fail' and i == 1:
                code = 'raise SystemExit(7)'
            if mode == 'deadline':
                code = "import pathlib,time; time.sleep(2); pathlib.Path(%r).touch()" % str(d / 'escaped')
            commands.append({'argv': [sys.executable, '-B', '-c', code]})
        if mode == 'deadline':
            for d, c, _, _ in self.entries:
                c['deadlines']['workUntil'] = iso(time.time() + .15)
                k.write(d / 'run.json', c)
            self.a['fixtures'] = [{'runId': c['runId'], 'namespace': c['namespace'],
                                   'namespaceUid': b['namespace']['uid'], 'runSha256': k.digest(d / 'run.json')}
                                  for d, c, _, b in self.entries]
            self.release()
        def observe(c, *args):
            return copy.deepcopy(next(b for _, config, _, b in self.entries if config['runId'] == c['runId']))
        def join(d, c, b, current):
            times = k.document(d / 'child.json')
            return self.point(d, c, b, start=times['start'], end=times['end'])
        output = self.root / ('matrix-' + mode)
        with ExitStack() as stack:
            stack.enter_context(patch.object(k, 'load', side_effect=load))
            stack.enter_context(patch.object(k, 'active_baseline', side_effect=lambda d: next(b for path, _, _, b in self.entries if path == d)))
            stack.enter_context(patch.object(k, 'observe', side_effect=observe))
            stack.enter_context(patch.object(e, 'matrix_plan', return_value={'commands': commands, 'contention': 'synthetic shared host'}))
            stack.enter_context(patch.object(e, 'actor', return_value={}))
            stack.enter_context(patch.object(e, 'assess', return_value={}))
            stack.enter_context(patch.object(m, 'joined_point', side_effect=join))
            value = m.run(self.value, output)
        return value

    def test_real_concurrent_children_join(self):
        result = self.run_synthetic()
        self.assertEqual(result['verdict'], 'OBSERVED_CONCURRENT_FIXTURES')
        self.assertGreater(result['concurrency']['seconds'], 0)
        self.assertEqual(result['capacityAcceptance'], 'NOT_GRANTED')

    def test_worker_failure_preserves_successful_peer(self):
        result = self.run_synthetic('fail')
        self.assertEqual(result['code'], 'K8S_MATRIX_INCOMPLETE')
        self.assertEqual(result['fixtures'][0]['verdict'], 'OBSERVED')
        self.assertEqual(result['fixtures'][1]['code'], 'K8S_MATRIX_WORKER_FAILED')
        self.assertEqual(result['fixtures'][1]['workerExitCode'], 7)
        # Restore using new output; successful old evidence is preserved.
        for d, *_ in self.entries:
            if (d / 'load').exists():
                (d / 'load').rename(d / 'retained-synthetic-load')
        self.assertEqual(self.run_synthetic()['verdict'], 'OBSERVED_CONCURRENT_FIXTURES')
        print('RED_RESTORED K8S_MATRIX_WORKER_FAILED exit=7; healthy peer retained')

    def test_actual_deadline_terminates_workers(self):
        deadlines = [copy.deepcopy(c['deadlines']) for _, c, _, _ in self.entries]
        result = self.run_synthetic('deadline')
        self.assertEqual(result['code'], 'K8S_MATRIX_INCOMPLETE')
        self.assertTrue(all(r['workerExitCode'] == 124 for r in result['fixtures']))
        self.assertTrue(all(not (d / 'escaped').exists() for d, *_ in self.entries))
        for (d, c, _, _), deadline in zip(self.entries, deadlines):
            c['deadlines'] = deadline
            k.write(d / 'run.json', c)
        self.a['fixtures'] = [{'runId': c['runId'], 'namespace': c['namespace'],
                               'namespaceUid': b['namespace']['uid'], 'runSha256': k.digest(d / 'run.json')}
                              for d, c, _, b in self.entries]
        self.release()
        self.assertEqual(self.run_synthetic()['verdict'], 'OBSERVED_CONCURRENT_FIXTURES')
        print('RED_RESTORED K8S_MATRIX_WORKER_FAILED exit=124; independent timeout terminated real children')


if __name__ == '__main__':
    unittest.main()
