import copy
import importlib.util
import io
import os
import signal
import threading
import time
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from protocol import binding, validate_message, Channel, traffic_verdict, server_verdict, TRAFFIC_FILES
import traffic_probe


def selected():
    return {'version': 1, 'profile': 'joined-external-generator-v1', 'runId': 'external-test',
            'cloudId': 'external-test-' + 'a' * 12, 'nonce': 'b' * 32, 'cell': 1, 'tenants': 2,
            'appAddress': '10.8.0.2', 'generatorAddress': '10.8.0.3', 'port': 18080,
            'expiresAt': 11800, 'pair': {'core': 'c' * 40, 'deploy': 'd' * 40},
            'imageId': 'sha256:' + 'e' * 64, 'k6Image': 'grafana/k6@sha256:' + 'f' * 64, 'sourceSha256': '1' * 64}


class Contract(unittest.TestCase):
    def test_external_idle_keeps_after_bookend_on_observer_refusal(self):
        import app
        primary = RuntimeError('SYNTHETIC_IDLE_REFUSED')
        @contextmanager
        def observe(*args):
            yield SimpleNamespace(result={'verdict': 'PASS'})
            raise primary
        @contextmanager
        def sample(*args):
            yield
        events = []
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(app.a, 'frozen'), mock.patch.object(app.a, 'quiet'), \
             mock.patch.object(app.a, 'verify'), mock.patch.object(app.a, 'readiness'), \
             mock.patch.object(app.a, 'psql') as sql, \
             mock.patch.object(app.a, 'phase_snapshot', side_effect=lambda d, out, name: events.append((out.name, name))), \
             mock.patch.object(app.a, 'sampling', side_effect=sample), \
             mock.patch.object(app.a, 'observe_progress', side_effect=observe), \
             mock.patch.object(app.time, 'sleep') as sleep:
            with self.assertRaises(RuntimeError) as caught:
                app.idle(Path(folder), {})
            self.assertIs(caught.exception, primary)
            self.assertEqual(sql.call_count, 2)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [60, 120])
        self.assertEqual(events, [('idle-disabled', 'before'), ('idle-disabled', 'after'), ('idle', 'before'), ('idle', 'after')])

    def test_positive_and_layout_refusals(self):
        b = selected()
        self.assertEqual(binding(b, 1000), b)
        for key, value in [('generatorAddress', b['appAddress']), ('appAddress', '127.0.0.1'), ('appAddress', '8.8.8.8'),
                           ('port', 22), ('expiresAt', 1500), ('cell', True), ('profile', 'joined-pilot-v1')]:
            bad = {**b, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                binding(bad, 1000)
        with self.assertRaises(RuntimeError):
            binding({**b, 'postgresCredential': 'fixture-refused'}, 1000)

    def test_exact_node_nonce_sequence_and_stage(self):
        b = selected()
        row = {'version': 1, 'runId': b['runId'], 'nonce': b['nonce'], 'cell': 1, 'node': 'controller', 'sequence': 1, 'kind': 'load-start', 'payload': {}}
        self.assertEqual(validate_message(row, b, 'controller', 1, 'load-start'), {})
        for key, value in [('runId', 'other-run'), ('nonce', 'a' * 32), ('node', 'generator-0'), ('sequence', 2), ('cell', 2), ('kind', 'finish')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate_message({**row, key: value}, b, 'controller', 1, 'load-start')
        with self.assertRaises(RuntimeError):
            validate_message(row, b, 'controller', 2, 'load-start')  # replay is not another acknowledgement

    def test_partial_line_is_bounded_and_eof_refuses(self):
        b = selected()
        for data, expected in [(b'{', 'TIMEOUT'), (b'', 'LOST')]:
            read_fd, write_fd = os.pipe()
            with os.fdopen(read_fd, 'rb', buffering=0) as stream:
                channel = Channel(b, 'app-0', incoming=stream, outgoing=io.StringIO(), clock=lambda: 1000)
                if data:
                    os.write(write_fd, data)
                else:
                    os.close(write_fd)
                start = time.monotonic()
                try:
                    with self.assertRaisesRegex(RuntimeError, expected):
                        channel.receive('load-start', maximum=.03)
                    self.assertLess(time.monotonic() - start, .3)
                finally:
                    if data: os.close(write_fd)

    def test_buffered_two_lines_and_duplicate_refusal(self):
        b = selected()
        row = {'version': 1, 'runId': b['runId'], 'nonce': b['nonce'], 'cell': 1, 'node': 'controller', 'sequence': 1, 'kind': 'load-start', 'payload': {}}
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, (json.dumps(row) + '\n' + json.dumps(row) + '\n').encode())
            with os.fdopen(read_fd, 'rb', buffering=0) as stream:
                channel = Channel(b, 'app-0', incoming=stream, outgoing=io.StringIO(), clock=lambda: 1000)
                self.assertEqual(channel.receive('load-start', maximum=.03), {})
                with self.assertRaisesRegex(RuntimeError, 'BINDING'):
                    channel.receive('load-start', maximum=.03)
        finally: os.close(write_fd)

    def test_generated_client_has_no_privileged_process_path(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / 'probe.js'
            result = traffic_probe.generate(HERE.parents[2], file)
            code = file.read_text()
            executable = '\n'.join(line for line in code.splitlines() if not line.lstrip().startswith('//'))
            for token in ('child_process', 'docker', 'psqlAsync', 'recoveryObserve', 'composeArgs'):
                self.assertNotIn(token, executable)
            self.assertIn("transports: ['polling']", code)
            self.assertIn("s.socket.emit('authorize'", code)
            self.assertIn("'EXTERNAL_RESTART_COMMAND_FAILED'", code)
            self.assertIn("measurement:'UNMEASURED'", code)
            self.assertFalse(result['privateAuthority'])
            subprocess.run(['node', '--check', file], check=True)

    def test_generator_source_anchor_is_a_semantic_guard(self):
        text = 'one matching anchor'
        self.assertEqual(traffic_probe.replace_once(text, 'matching', 'current'), 'one current anchor')
        with self.assertRaises(RuntimeError):
            traffic_probe.replace_once(text, 'retired anchor', 'current')
        with self.assertRaises(RuntimeError):
            traffic_probe.replace_once('matching matching', 'matching', 'current')

    def test_same_traffic_predicates_and_scope(self):
        probe = {'prime': {'primed': 4}, 'window': {'deliveredFrames': 8, 'expectedFrames': 8, 'writes': {'failed': 0},
                 'writeToEvaluationMs': {'measurement': 'UNMEASURED', 'reason': 'Per-write SQL latency observer NOT_RUN; strict progress remains app-side; no cross-host latency inferred'}},
                 'restart': {'stockRecovered': 4, 'sockets': 4}}
        metrics = {name: {'count': 0} for name in ('writes_refused', 'responses_refused', 'dropped_iterations')}
        metrics['http_req_failed'] = {'rate': 0}
        self.assertTrue(traffic_verdict(probe, metrics, 2))
        wrapped = {key: {'values': row} for key, row in metrics.items()}
        self.assertTrue(traffic_verdict(probe, wrapped, 2))
        for value in (False, float('nan'), float('inf'), None):
            bad = copy.deepcopy(wrapped);bad['writes_refused']['values']['count'] = value
            with self.subTest(invalidMetric=value), self.assertRaises(RuntimeError):
                traffic_verdict(probe, bad, 2)
        bad = copy.deepcopy(metrics);del bad['responses_refused']
        with self.assertRaisesRegex(RuntimeError, 'METRIC_MISSING'):
            traffic_verdict(probe, bad, 2)
        for section, key, value in [('prime', 'primed', 3), ('window', 'deliveredFrames', 7), ('restart', 'stockRecovered', 3)]:
            bad = copy.deepcopy(probe)
            bad[section][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                traffic_verdict(bad, metrics, 2)
        for key, field in [('writes_refused', 'count'), ('responses_refused', 'count'), ('dropped_iterations', 'count'), ('http_req_failed', 'rate')]:
            bad = copy.deepcopy(metrics)
            bad[key][field] = 1
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                traffic_verdict(probe, bad, 2)
        bad = copy.deepcopy(probe)
        bad['window']['writeToEvaluationMs'] = {'p95': 0}
        with self.assertRaises(RuntimeError):
            traffic_verdict(bad, metrics, 2)

class ServerEvidence(unittest.TestCase):
    def test_oracle_recovery_metrics_are_independent_required_predicates(self):
        b = selected()
        oracle, recovered, measured = {'verdict': 'GREEN', 'uncertain': 0}, {'verdict': 'PASS', 'missing': 0}, {'complete': True}
        generator = {'runId': b['runId'], 'nonce': b['nonce'], 'complete': True, 'samples': [{'cpuUsec': 1, 'rssBytes': 1, 'networkBytes': 1}]}
        self.assertTrue(server_verdict(oracle, recovered, measured, generator, b))
        for value, index in [({'verdict': 'RED', 'uncertain': 0}, 0), ({'verdict': 'GREEN', 'uncertain': False}, 0),
                             ({'verdict': 'PASS', 'missing': 1}, 1), ({'verdict': 'PASS', 'missing': False}, 1), ({'complete': False}, 2), ({**generator, 'complete': False}, 3), ({**generator, 'samples': []}, 3)]:
            args = [oracle, recovered, measured, generator, b];args[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(RuntimeError):
                server_verdict(*args)

    def test_supervisor_hangup_and_abort_unwind_cleanup_once_and_never_pass(self):
        import generator
        for terminating in (signal.SIGHUP, signal.SIGTERM):
            trace = []
            previous = {kind: signal.getsignal(kind) for kind in (signal.SIGHUP, signal.SIGTERM)}
            def interrupted_session(*args):
                try:
                    signal.raise_signal(terminating)
                    trace.append('false-pass')
                finally:
                    trace.append('owned-cleanup')
                    # A second controller signal cannot interrupt or reenter it.
                    signal.raise_signal(signal.SIGHUP)
                    signal.raise_signal(signal.SIGTERM)
                    trace.append('cleanup-finished')
            with tempfile.TemporaryDirectory() as scratch:
                binding_file = Path(scratch) / 'binding.json'
                binding_file.write_text('{}')
                with mock.patch.object(sys, 'argv', ['generator.py', '--directory', scratch, '--binding', str(binding_file)]), \
                     mock.patch.object(generator, 'session', side_effect=interrupted_session):
                    with self.assertRaisesRegex(RuntimeError, 'EXTERNAL_CONTROLLER_LOST'):
                        generator.main()
            self.assertEqual(trace, ['owned-cleanup', 'cleanup-finished'])
            self.assertEqual({kind: signal.getsignal(kind) for kind in previous}, previous)

    def test_metrics_timeout_and_bound_never_publish_complete(self):
        import generator
        b = selected()
        class Stop:
            def is_set(self): return False
            def wait(self, amount): pass
        process = SimpleNamespace(pid=os.getpid(), poll=lambda: None)
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch) / 'metrics.json'
            good = SimpleNamespace(returncode=0, stdout='{"CPUPerc":"1%"}')
            with mock.patch.object(generator.subprocess, 'run', side_effect=[good, subprocess.TimeoutExpired('docker', 10)]):
                generator.sample(process, b, out, Stop(), 'owned-k6')
            value = json.loads(out.read_text())
            self.assertIs(value['complete'], False)
            self.assertEqual(value['refusal'], 'EXTERNAL_GENERATOR_METRICS_REFUSED')
            self.assertEqual(len(value['samples']), 1)
            self.assertIsNotNone(value['samples'][0]['k6'])
            with mock.patch.object(generator.subprocess, 'run', side_effect=[good, RuntimeError('EXTERNAL_METRICS_BOUND')]):
                generator.sample(process, b, out, Stop(), 'owned-k6')
            value = json.loads(out.read_text())
            self.assertIs(value['complete'], False)
            self.assertEqual(value['refusal'], 'EXTERNAL_METRICS_BOUND')
            self.assertEqual(len(value['samples']), 1)

class AppPhases(unittest.TestCase):
    def test_actual_producer_exports_the_complete_public_transfer_manifest(self):
        import app
        with tempfile.TemporaryDirectory() as scratch:
            d = Path(scratch)
            (d / 'dependencies').mkdir();(d / 'k6').mkdir()
            for name in ('package.json', 'package-lock.json'): (d / 'dependencies' / name).write_text('{}')
            (d / 'tenants.private.json').write_text('[{}]')
            (d / 'k6/workload.js').write_text('// public workload fixture\n')
            b = selected();m = {'externalBinding': b, 'owner': 'a' * 32, 'generator': {}, 'settingsFingerprint': {'sha256': 'f' * 64}}
            with mock.patch.object(app, 'load', return_value=(d, m, b)):
                descriptor = app.export_traffic(d, b)
            self.assertEqual(set(descriptor['files']), set(TRAFFIC_FILES))
            self.assertEqual({p.name for p in (d / 'traffic-export').iterdir()}, set(TRAFFIC_FILES) | {'traffic.json'})
            self.assertIn('recovery.cjs', descriptor['files'])
            self.assertNotIn('env.json', descriptor['files'])

    def test_actual_export_is_accepted_by_privilege_scoped_generator_preparation(self):
        import app, generator
        import hashlib
        with tempfile.TemporaryDirectory() as scratch:
            d = Path(scratch)
            (d / 'dependencies').mkdir();(d / 'k6').mkdir()
            for name in ('package.json', 'package-lock.json'): (d / 'dependencies' / name).write_text('{}')
            (d / 'tenants.private.json').write_text('[{},{}]')
            (d / 'k6/workload.js').write_text('// synthetic workload')
            digest = hashlib.sha256(b'{}').hexdigest()
            client_digest = hashlib.sha256(b'// synthetic client').hexdigest()
            b = selected()
            expected = {'pair': b['pair'], 'servingImageId': b['imageId'], 'tools': {},
                        'packageSha256': digest, 'lockSha256': digest,
                        'client': {'version': 'synthetic', 'entrySha256': client_digest}}
            m = {'externalBinding': b, 'owner': 'a'*32, 'generator': expected, 'settingsFingerprint': {'sha256': 'f'*64}}
            with mock.patch.object(app, 'load', return_value=(d, m, b)):
                produced = app.export_traffic(d, b)
            incoming = d / 'traffic-export'
            entry = incoming / 'dependencies/node_modules/socket.io-client/index.js'
            def npm(*args):
                entry.parent.mkdir(parents=True)
                entry.write_text('// synthetic client')
                return SimpleNamespace(wait=lambda **kw: 0, poll=lambda: 0)
            with mock.patch.object(generator.os, 'geteuid', return_value=0), mock.patch.object(generator.os, 'chown'), \
                 mock.patch.object(generator.pwd, 'getpwuid', return_value=SimpleNamespace(pw_name='nsload', pw_gid=1001)), \
                 mock.patch.object(generator, 'child', side_effect=npm), \
                 mock.patch.object(generator.subprocess, 'check_output', side_effect=['nsload', json.dumps({'entry': str(entry), 'version': 'synthetic'})]):
                self.assertEqual(generator.prepare(incoming, b), produced)
            provenance = json.loads((incoming / 'generator-provenance.json').read_text())
            self.assertFalse(provenance['dockerAuthority'])
            self.assertEqual(provenance['trafficGroups'], ['nsload'])
            # A producer digest change must fail before installing anything.
            (incoming / 'workload.js').chmod(0o600)
            (incoming / 'workload.js').write_text('// changed synthetic workload')
            with mock.patch.object(generator.os, 'geteuid', return_value=0), \
                 mock.patch.object(generator.pwd, 'getpwuid', return_value=SimpleNamespace(pw_name='nsload', pw_gid=1001)), \
                 mock.patch.object(generator.subprocess, 'check_output', return_value='nsload'), mock.patch.object(generator, 'child') as install:
                with self.assertRaisesRegex(RuntimeError, 'EXPORT_CHANGED'): generator.prepare(incoming, b)
                install.assert_not_called()

    def test_actual_app_session_requires_readiness_progress_and_server_recovery(self):
        import app
        transcript = []
        b = selected()
        m = {'externalBinding': b, 'owner': 'a' * 32, 'tenants': 2}
        class Protocol:
            def __init__(self, binding, node): pass
            def send(self, kind, payload=None): transcript.append(('send', kind))
            def receive(self, kind, maximum=0):
                transcript.append(('receive', kind))
                return {'primed': 4} if kind == 'client-primed' else {}
        @contextmanager
        def observation(*args):
            transcript.append(('observe', 'load'))
            yield SimpleNamespace(result={'verdict': 'PASS'})
        @contextmanager
        def sample(*args): yield
        with tempfile.TemporaryDirectory() as scratch:
            d = Path(scratch)
            patches = [mock.patch.object(app, 'load', return_value=(d, m, b)), mock.patch.object(app, 'Channel', Protocol),
                mock.patch.object(app, 'idle', side_effect=lambda *args: transcript.append(('readiness', 'PASS'))),
                mock.patch.object(app.a, 'sampling', sample), mock.patch.object(app.a, 'phase_snapshot'),
                mock.patch.object(app.a, 'psql'), mock.patch.object(app.a, 'observe_progress', observation),
                mock.patch.object(app, 'recovery', side_effect=lambda d,m,mode,*args: transcript.append(('private-recovery', mode)) or {'verdict':'PASS','missing':0}),
                mock.patch.object(app, 'restart', return_value=({'commandMs': 5}, 1000)), mock.patch.object(app, 'health', return_value={}),
                mock.patch.object(app.a, 'progress_summary', return_value={'verdict':'PASS'}), mock.patch.object(app, 'summarize', return_value={'verdict':'PASS'})]
            from contextlib import ExitStack
            with ExitStack() as stack:
                for patch in patches: stack.enter_context(patch)
                app.session(d, b)
            self.assertLess(transcript.index(('readiness', 'PASS')), transcript.index(('send', 'app-ready')))
            self.assertLess(transcript.index(('private-recovery', 'baseline')), transcript.index(('send', 'restart-ready')))
            self.assertLess(transcript.index(('private-recovery', 'recovery')), transcript.index(('send', 'server-recovery-complete')))
            self.assertLess(transcript.index(('receive', 'finish')), transcript.index(('send', 'cell-complete')))
        transcript.clear()
        with mock.patch.object(app, 'load', return_value=(Path('/unused'), m, b)), mock.patch.object(app, 'Channel', Protocol), mock.patch.object(app, 'idle', side_effect=RuntimeError('readiness-not-met')):
            with self.assertRaisesRegex(RuntimeError, 'readiness-not-met'): app.session('/unused', b)
        self.assertNotIn(('send', 'app-ready'), transcript)

if __name__ == '__main__':
    unittest.main()
