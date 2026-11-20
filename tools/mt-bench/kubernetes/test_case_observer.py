"""case_observer: per-Pod usage, CPU model per node, bounded role-log followers. No cluster."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

import case_observer as o

RUN = 'k2-case'
CPUINFO = 'processor\t: 0\nmodel name\t: Intel(R) Xeon(R) Platinum 8168 CPU @ 2.70GHz\nflags\t: x\n'


def pod(name, node, labels, containers):
    return {'metadata': {'name': name, 'labels': {o.LABEL: RUN, **labels}}, 'spec': {'nodeName': node},
            'status': {'phase': 'Running', 'containerStatuses': [{'name': c, 'state': {'running': {}}} for c in containers]}}


class Fake:
    """Answers the observer's kubectl reads; follow() returns a finite fake log stream."""

    def __init__(self, logs):
        self.logs, self.follows = logs, []
        self.pods = [pod('evaluator-0', 'node-a', {'app': 'ev'}, ['evaluator']),
                     pod('evaluator-1', 'node-a', {'app': 'ev'}, ['evaluator']),
                     pod('api-5d-x', 'node-a', {'app': 'api'}, ['api'])]

    def __call__(self, *args, timeout=12):
        if args[:2] == ('get', 'ns'):
            return json.dumps({'metadata': {'uid': 'ns-uid', 'labels': {o.LABEL: RUN}}})
        if args[:2] == ('get', 'pods'):
            return json.dumps({'items': self.pods})
        if args[:2] == ('top', 'node'):
            return 'node-a 2400m 15% 3000Mi 10%\n'
        if args[:2] == ('top', 'pods'):
            return ('evaluator-0 evaluator 1050m 500Mi\nevaluator-1 evaluator 640m 410Mi\n'
                    'api-5d-x api 400m 300Mi\n')
        if args[0] == 'exec' and args[-1] == '/proc/cpuinfo':
            return CPUINFO
        raise AssertionError(args)

    def follow(self, name, container, since=None):
        self.follows.append((name, container, since))
        lines = self.logs.get((name, len([f for f in self.follows if f[0] == name])), [])
        process = type('P', (), {})()
        process.stdout = io.BytesIO(b''.join(lines))
        process.wait = lambda timeout=None: 0
        process.poll = lambda: 0
        process.terminate = lambda: None
        return process


class Clock:
    def __init__(self, samples):
        self.t, self.samples = 0.0, samples

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        # Let the fake log streams drain so restarts are deterministic.
        for thread in threading.enumerate():
            if thread is not threading.main_thread():
                thread.join(2)
        self.t += seconds


def case(tmp, role_env):
    d = Path(tmp)/'case'
    (d/'runtime').mkdir(parents=True)
    write = lambda name, value: (d/name).write_text(json.dumps(value))
    write('environment.json', {'context': 'ctx', 'namespace': 'k1cc-' + RUN, 'runId': RUN, 'cleanupDeadlineSeconds': 100})
    write('native-run-template.json', {'nativeLoad': {'nodeName': 'node-a'}})
    write('binding-inputs.json', {'slices': {'evaluator': 2}, **({'roleEnv': role_env} if role_env else {})})
    spec = lambda name, label: {'apiVersion': 'apps/v1', 'kind': 'StatefulSet' if name == 'evaluator' else 'Deployment',
                                'metadata': {'name': name}, 'spec': {'selector': {'matchLabels': {'app': label}},
                                'template': {'spec': {'containers': [{'name': name}]}}}}
    write('render.json', {'apiVersion': 'v1', 'kind': 'List', 'items': [spec('evaluator', 'ev'), spec('api', 'api')]})
    write('runtime/custody.json', {'namespaceUid': 'ns-uid'})
    write('runtime/stages.json', [{'stage': o.TRAFFIC}])
    return o.Case(d)


class Observer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def observe(self, role_env, logs=None, cap=1 << 20, samples=2):
        self.round = getattr(self, 'round', 0) + 1
        root = Path(self.tmp.name)/str(self.round)
        c = case(root, role_env)
        fake = Fake(logs or {})
        clock = Clock(samples)
        stop = lambda: clock.t >= samples * 15
        out = root/'out'
        original = o.sample
        def no_slot(case_, kubectl, state):
            stages = case_.runtime/'stages.json'
            stages.write_text(json.dumps([{'stage': 'serving'}]))  # no psql exec in this fake
            row = original(case_, kubectl, state)
            stages.write_text(json.dumps([{'stage': o.TRAFFIC}]))
            row['stage'] = o.TRAFFIC
            return row
        o.sample = no_slot
        try:
            state = o.observe(c, out, interval=15, cap=cap, kubectl=fake, stop=stop, clock=clock)
        finally:
            o.sample = original
        for follower in state['followers'].values():
            follower.stop()
        return c, out, fake

    def test_each_evaluator_ordinal_and_the_node_cpu_model_are_reported(self):
        c, out, _ = self.observe(None)
        summary = o.summarize(c, out)
        pods = summary['steadyPodUsage']
        self.assertEqual(pods['evaluator-0']['evaluator']['cpuMillicores']['median'], 1050)
        self.assertEqual(pods['evaluator-1']['evaluator']['cpuMillicores']['median'], 640)
        self.assertEqual(pods['evaluator-1']['node'], 'node-a')
        role = summary['steadyContainerUsage']['evaluator']
        self.assertEqual((role['pods'], role['cpuMillicores']['median']), (2, 1690))
        self.assertEqual(summary['steadyContainerUsage']['api']['pods'], 1)
        self.assertEqual(summary['nodes'][0]['name'], 'node-a')
        self.assertEqual(summary['nodes'][0]['cpuModel'], 'Intel(R) Xeon(R) Platinum 8168 CPU @ 2.70GHz')
        self.assertIsNone(summary['podLogs'])
        self.assertFalse((out/'podlogs').exists(), 'no follower without roleEnv')

    def test_role_logs_follow_each_pod_dedupe_on_restart_and_stop_at_cap(self):
        first = [b'2026-11-20T01:00:00.1Z a\n', b'2026-11-20T01:00:00.2Z b\n']
        again = [b'2026-11-20T01:00:00.2Z b\n', b'2026-11-20T01:00:00.25Z c\n']
        logs = {('evaluator-0', 1): first, ('evaluator-0', 2): again, ('evaluator-1', 1): [b'2026-11-20T01:00:01Z x\n']}
        c, out, fake = self.observe({'evaluator': [{'name': 'NS_M7_DIAGNOSTICS', 'value': '1'}]}, logs)
        self.assertEqual((out/'podlogs'/'evaluator-0.evaluator.log').read_bytes(), b''.join(first) + again[1])
        self.assertEqual((out/'podlogs'/'evaluator-1.evaluator.log').read_bytes(), logs[('evaluator-1', 1)][0])
        self.assertNotIn('api-5d-x', {f[0] for f in fake.follows})
        self.assertEqual(fake.follows[2], ('evaluator-0', 'evaluator', '2026-11-20T01:00:00.200000000Z'))
        # Bounded: a follower stops writing at its cap and is not restarted.
        c, out, fake = self.observe({'evaluator': []}, {('evaluator-0', 1): first * 10}, cap=60)
        records = {r['pod']: r for r in json.loads((out/'podlogs'/'followers.json').read_text())}
        self.assertTrue(records['evaluator-0']['truncatedAtCap'])
        self.assertLessEqual(records['evaluator-0']['bytes'], 60)
        self.assertEqual(records['evaluator-0']['starts'], 1)


if __name__ == '__main__':
    unittest.main()


class Traffic(Fake):
    """A case in traffic: PostgreSQL and two evaluator ordinals; records every exec."""

    def __init__(self):
        super().__init__({})
        ev = {'app': 'ev', 'app.kubernetes.io/component': 'evaluator'}
        self.pods = [pod('evaluator-0', 'node-a', ev, ['evaluator']), pod('evaluator-1', 'node-a', ev, ['evaluator']),
                     pod('postgres-0', 'node-a', {'app': 'pg'}, ['postgres'])]
        self.execs = []

    def __call__(self, *args, timeout=12):
        if args[0] == 'exec':
            self.execs.append(args)
            return ''
        return super().__call__(*args, timeout=timeout)


class FakePrometheus:
    """Stands in for LocalPrometheus: answers each query from a table, records the bookend."""
    queries = []

    def __init__(self, archive):
        self.archive = archive

    def query(self, expr, at):
        FakePrometheus.queries.append((expr, at))
        if expr.startswith('max by (queryid, query)'):
            return [{'labels': {'queryid': '7', 'query': 'SELECT $1'}, 'value': 1.0}]
        if expr.startswith('topk(25, sum by (queryid) (increase(pg_stat_statements_seconds_total'):
            return [{'labels': {'queryid': '7'}, 'value': 2.5}]
        return [{'labels': {'pod': 'evaluator-0'}, 'value': 0.5}]

    def close(self):
        pass


class Capture(unittest.TestCase):
    def test_traffic_samples_make_no_exec(self):
        # The hand capture (/proc threads, walsender, pg_stat_statements, slot) is retired on
        # Kubernetes: with the node's CPU model known, a traffic sample makes no exec at all.
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        c = case(tmp.name, None)
        out = Path(tmp.name)/'out'; out.mkdir()
        fake = Traffic()
        state = {'out': out, 'nodes': {'node-a': {'cpuModel': 'X'}}, 'followers': {}, 'cap': 1}
        rows = [o.sample(c, fake, state) for _ in range(4)]
        self.assertEqual(fake.execs, [])
        self.assertFalse(any(key in row for row in rows for key in ('threads', 'walsender', 'slot')))
        self.assertEqual(list(out.glob('pg_stat_statements-*.json')), [])

    def test_prometheus_figures_need_a_snapshot(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        c = case(tmp.name, None)
        self.assertEqual(o.prometheus_figures(c, 0, 1000, local=FakePrometheus)['verdict'], 'UNMEASURED')
        (c.d/'load').mkdir()
        (c.d/'load'/'metrics-snapshot.json').write_text(json.dumps({'verdict': 'UNMEASURED', 'code': 'K8S_METRICS_SNAPSHOT_UNMEASURED'}))
        value = o.prometheus_figures(c, 0, 1000, local=FakePrometheus)
        self.assertEqual((value['verdict'], value['reason']), ('UNMEASURED', 'K8S_METRICS_SNAPSHOT_UNMEASURED'))

    def test_prometheus_figures_at_the_steady_bookends(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        c = case(tmp.name, None)
        (c.d/'load').mkdir()
        (c.d/'load'/'metrics-snapshot.json').write_text(json.dumps({'verdict': 'OBSERVED', 'file': 'metrics-tsdb.tar', 'sha256': 'ab'}))
        # No k6 executor windows: the controller's load window is the bookend.
        (c.d/'load'/'window.json').write_text(json.dumps({'loadStartedAt': 1000.0, 'loadEndedAt': 1600.5}))
        FakePrometheus.queries = []
        value = o.prometheus_figures(c, None, None, local=FakePrometheus)
        self.assertEqual(value['verdict'], 'OBSERVED')
        self.assertEqual(value['window'], {'basis': 'controller load window', 'startMs': 1000000.0, 'endMs': 1600500.0, 'seconds': 600})
        self.assertEqual({at for _, at in FakePrometheus.queries}, {1600.5})
        self.assertTrue(all('[600s]' in expr for expr, _ in FakePrometheus.queries))
        self.assertEqual(set(value['figures']), set(o.QUERIES) - {'statementText'})
        self.assertEqual(value['figures']['topStatementsSeconds'], [{'labels': {'queryid': '7'}, 'value': 2.5, 'query': 'SELECT $1'}])

    def test_delivery_span_and_gap_from_receiver_trace(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        logs = Path(tmp.name)/'podlogs'; logs.mkdir()
        line = lambda at, ms, pos: ('2026-11-20T00:00:00Z PGSTREAM_RECEIVER_TRACE ' + json.dumps(
            {'at': at, 'request': 1, 'event': 'response-finished', 'elapsedMs': ms, 'position': pos, 'rows': 3, 'status': 200, 'dropped': 0}) + '\n')
        (logs/'evaluator-0.evaluator.log').write_text(line(1010, 10, '0/A') + line(1100, 20, '0/B') + 'other line\n')
        (logs/'evaluator-1.evaluator.log').write_text(line(1030, 25, '0/A') + line(1090, 5, '0/B'))
        value = o.delivery(Path(tmp.name))
        self.assertEqual(value['batches'], 2)
        self.assertEqual(value['deliverySpanMs']['max'], 30)   # 0/A: received 1000, last response 1030
        self.assertEqual(value['interBatchGapMs']['median'], 50)  # 0/B first receipt 1080 - 1030
        self.assertEqual(o.delivery(Path(tmp.name)/'none')['verdict'], 'UNMEASURED')
