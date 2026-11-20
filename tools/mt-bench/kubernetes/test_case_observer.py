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
    """A case in traffic: PostgreSQL and two evaluator ordinals answer the capture reads."""

    def __init__(self):
        super().__init__({})
        ev = {'app': 'ev', 'app.kubernetes.io/component': 'evaluator'}
        self.pods = [pod('evaluator-0', 'node-a', ev, ['evaluator']), pod('evaluator-1', 'node-a', ev, ['evaluator']),
                     pod('postgres-0', 'node-a', {'app': 'pg'}, ['postgres'])]
        self.ticks, self.calls, self.statements = {}, 0, 0

    def __call__(self, *args, timeout=12):
        if args[0] == 'exec' and args[3] == 'postgres' and 'psql' in args:
            start = args.index('psql')
            sql = [args[i + 1] for i, a in enumerate(args) if a == '-c' and i > start]
            if sql == [o.SLOT_SQL]:
                return json.dumps({'active': True, 'confirmedLagBytes': 1000, 'retainedWalBytes': 2000})
            if o.WALSENDER_SQL in sql:
                return '\n'.join(json.dumps([{'pid': 7, 'state': 'active', 'waitEventType': 'IPC' if i else 'Client',
                                              'waitEvent': 'WalSenderWriteData' if not i else 'x'}]) + ('\n' if i < 4 else '')
                                 for i in range(5))
            if o.PGSS_SQL in sql:
                self.statements += 1
                return json.dumps({'at': 'T%d' % self.statements, 'rows': [
                    {'queryid': '1', 'dbid': 5, 'userid': 9, 'toplevel': True, 'calls': 10 * self.statements,
                     'total_exec_time': 4.0 * self.statements, 'rows': self.statements, 'query': 'SELECT $1'}]}) + '\n'
        if args[0] == 'exec' and args[3] == 'evaluator' and args[-2] == '-e':
            name = args[1]
            seen = self.ticks.setdefault(name, 0)
            self.ticks[name] += 1
            # Per second of uptime: main thread 0.9 core, one helper thread 0.1.
            return json.dumps({'uptime': 100 + seen, 'tasks': [[1, 'node', 90 * seen, 0], [7, 'V8 Worker', 10 * seen, 0]]})
        return super().__call__(*args, timeout=timeout)


class Capture(unittest.TestCase):
    def test_threads_walsender_and_statement_snapshots_are_recorded_and_reduced(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        c = case(tmp.name, None)
        out = Path(tmp.name)/'out'; out.mkdir()
        fake, state = Traffic(), {'out': out, 'nodes': {}, 'followers': {}, 'cap': 1}
        rows = [o.sample(c, fake, state) for _ in range(4)]
        self.assertTrue((out/'pg_stat_statements-start.json').is_file() and (out/'pg_stat_statements-latest.json').is_file())
        (c.runtime/'stages.json').write_text(json.dumps([{'stage': 'observe correctness'}]))
        o.sample(c, fake, state)
        self.assertTrue((out/'pg_stat_statements-end.json').is_file())
        self.assertEqual(set(rows[0]['threads']), {'evaluator-0', 'evaluator-1'})
        with (out/'samples.jsonl').open('w') as f:
            for row in rows:
                f.write(json.dumps(row) + '\n')
        summary = o.summarize(c, out)
        self.assertEqual(summary['evaluatorThreads']['evaluator-1']['mainThreadCores']['median'], 0.9)
        self.assertEqual(summary['evaluatorThreads']['evaluator-1']['otherThreadsCores']['median'], 0.1)
        self.assertEqual(summary['evaluatorThreads']['evaluator-0']['busiestOtherThreads'], [('V8 Worker', 0.1)])
        self.assertEqual(summary['walsender']['byWaitEvent']['Client:WalSenderWriteData'], 4)
        self.assertEqual(summary['walsender']['samples'], 20)
        statements = summary['pgStatStatements']
        self.assertEqual((statements['calls'], statements['totalMs']), (20, 8.0))  # start T1 to end T3

    def test_statement_snapshot_failure_is_recorded_not_raised(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        def broken(*args, timeout=12):
            raise subprocess.CalledProcessError(1, 'psql')
        o.statements(broken, Path(tmp.name), 'start')
        self.assertEqual(json.loads((Path(tmp.name)/'pg_stat_statements-start.json').read_text())['verdict'], 'UNMEASURED')
        self.assertEqual(o.statement_delta(Path(tmp.name))['verdict'], 'UNMEASURED')

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
