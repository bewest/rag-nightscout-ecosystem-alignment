"""Exercise the real stage, strict midpoint capture and owned process stop."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import execute
import kube_adapter as k
from test_adapter import A, B, fixture
from test_preload import page
from workloads.reduce import reduce_stage


PROBE = '''
import sys
import time
from pathlib import Path
assert sys.argv[sys.argv.index('--evalTimeout') + 1] == '120'
signal = Path(sys.argv[sys.argv.index('--signal') + 1])
signal.write_text(str(time.time()))
while not signal.with_name('.restart').exists():
    time.sleep(.04)
'''

DRIVER = '''
import json
import sys
import time
from pathlib import Path
def marker(name):
    event = json.dumps({'event': name, 'atMs': time.time_ns() // 1000000})
    print('level=info msg=' + json.dumps(event) + ' source=console', file=sys.stderr, flush=True)
assert '--log-output=stderr' in sys.argv
marker('jwt-setup-start')
time.sleep(SETUP)
marker('jwt-setup-end')
marker('scenario-first-iteration')
time.sleep(RUN)
Path(sys.argv[sys.argv.index('--summary-export') + 1]).write_text('{"metrics":{}}')
print('terminal stdout')
'''

K6_DRIVER = '''
import { sleep } from 'k6';
export const options = {vus: 1, iterations: 1};
function marker(event) { console.log(JSON.stringify({event, atMs: Date.now()})); }
export function setup() {
  marker('jwt-setup-start');
  sleep(SETUP);
  marker('jwt-setup-end');
}
export default function () {
  marker('scenario-first-iteration');
  sleep(RUN);
}
'''


class FailureCapture(unittest.TestCase):
    def trial(self, fail, signal=False, module=execute):
        """fail: a hard midpoint (untyped failed completion) stops the driver.
        signal: a not-ready midpoint without a hard reason is recorded; the run continues."""
        capture = os.environ.get('K8S_TEST_CAPTURE_DIR')
        if capture:
            retained = Path(capture) / ('refusal' if fail else 'midpoint-signal' if signal else 'delayed-setup')
            retained.mkdir(mode=0o700, parents=True)
            scratch = nullcontext(retained)
        else:
            scratch = tempfile.TemporaryDirectory()
        with scratch as temporary:
            d = Path(temporary)
            c, inventory, rendered, replies = fixture()
            c.update(tenants=2, tenantsFile=str(d/'tenants.json'), settingsFingerprint='b'*64,
                     baseUrl='http://127.0.0.1:18080',
                     workload={'loadSeconds':2, 'logicalPollingClients':0,
                               'probeEveryMs':3000, 'offeredRps':1, 'setupSeconds':15})
            c['completion'] = {'binding':{'kind':'evaluator-work-v2', 'pair':c['pins']['pair'],
                                          'imageId':c['pins']['appImageId'],
                                          'instrument':c['pins']['instrument']}}
            launch = os.environ.get('K8S_TEST_NATIVE_K6')
            driver = Path(launch) if launch else d/'driver'
            setup, run = (0.15, 8) if fail else (0.15, 2) if signal else (2.0, 0.2)
            script = (K6_DRIVER if launch else f'#!{sys.executable}\n' + DRIVER)
            script = script.replace('SETUP', str(setup)).replace('RUN', str(run))
            workload = d/'workload.js'
            workload.write_text(script)
            if not launch:
                driver.write_text(script)
                driver.chmod(0o700)
            c['driver'].update(node=sys.executable, dependencies=str(d),
                               k6=str(driver), k6Sha256=k.digest(driver))
            probe = d/'probe.cjs'
            probe.write_text(PROBE)
            k.write(d/'tenants.json', [{'id':i, 'host':'fixture.test', 'token':'synthetic'} for i in (A, B)])
            k.write(d/'packet.json', {'probe':{'kubernetesSha256':k.digest(probe)},
                                     'workload':{'adaptedSha256':k.digest(workload)}})
            k.write(d/'run.json', c)
            objects = k.validate(c, inventory, rendered)
            baseline = k.observe(c, objects, replies)
            tool = d/'kubectl'
            tool.touch()
            c['kubectl'] = str(tool)
            captures = []
            midpoint_logs = []
            out = d/'load'
            def run_rpc(argv, **kwargs):
                ready = not ((fail or signal) and len(captures) == 1)
                if not ready:
                    log = out/'k6.log'
                    midpoint_logs.append(log.read_bytes() if log.is_file() else b'')
                value = json.dumps(page(ready, failed=(1, 0) if fail and not ready else (0, 0))).encode()+b'\n'
                captures.append(value)
                return SimpleNamespace(returncode=0, stdout=value, stderr=b'')
            client = k.Client(c, run=run_rpc)
            import catchup
            with patch.object(catchup, 'run', return_value={'verdict':'PASS'}) as collected, \
                 patch.object(k.candidate, 'require'), patch.object(module, 'actor', return_value={}), \
                 patch.object(k, 'active_baseline', return_value=baseline), \
                 patch.object(k, 'observe', return_value=baseline), \
                 patch.object(k.shutil, 'which', return_value=str(tool)), \
                 patch.dict('os.environ', {'K6_NO_USAGE_REPORT':'true', 'K6_ADDRESS':'127.0.0.1:0'}), \
                 patch.object(module, 'assess_stage', return_value={'verdict':'OBSERVED'}) as assess:
                if fail:
                    with self.assertRaisesRegex(k.evaluator_progress.Refused, 'M7_EVALUATOR_PROGRESS_ERROR'):
                        module.execute(d, c, objects, client, load=True)
                    assess.assert_not_called()
                else:
                    self.assertEqual(module.execute(d, c, objects, client, load=True)['verdict'], 'OBSERVED')
                    assess.assert_called_once()
                    collected.assert_called_once()
                    self.assertEqual(k.document(out/'drain.json')['requestedSeconds'], 120)

            raw = out/'progress-midpoint.private.jsonl'
            self.assertTrue(raw.is_file(), 'typed midpoint response bytes were lost')
            self.assertEqual(raw.read_bytes(), captures[1])
            self.assertEqual(raw.stat().st_mode & 0o777, 0o600)
            response = k.document(out/'progress-midpoint-response.json')
            self.assertEqual(response['sourceDecode'], 'REFUSED' if fail or signal else 'PASS')
            decision = k.document(out/'progress-midpoint-signal.json')
            self.assertEqual(decision['action'], 'stop' if fail else 'continue')
            if signal:
                self.assertEqual(decision['strictRefusal']['code'], 'M7_EVALUATOR_PROGRESS_ERROR')
                self.assertEqual(decision['classification']['readiness']['NOT_READY'],
                                 {'EVALUATOR_CLINICAL_PROGRESS_STALLED': 2})
                self.assertTrue((out/'.restart').exists(), 'a midpoint signal stopped the driver')
                print('Midpoint signal recorded; driver continued to completion')
                return
            self.assertEqual(response['postObservation'], 'VERIFIED')
            self.assertEqual(response['captureBoundary'], 'client-response-sink')
            self.assertEqual(response['sha256'], k.digest(raw))
            events = out/'k6.log'
            self.assertEqual(events.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(b'scenario-first-iteration', (out/'k6-native.log').read_bytes())
            if fail:
                failure = k.document(out/'progress-midpoint-failure.json')
                self.assertEqual(failure['diagnostic']['failedRow']['code'],
                                 'EVALUATOR_CLINICAL_PROGRESS_STALLED')
                self.assertFalse((out/'progress-after.json').exists())
                self.assertFalse((out/'.restart').exists())
                self.assertEqual(decision['classification']['classes'].get('UNTYPED'), 1)
                stop = k.document(out/'stop-evidence.json')
                self.assertTrue(stop['progressRetained'], 'raw progress at the stop point was not retained')
                self.assertTrue((out/'progress-stop.private.jsonl').is_file())
                self.assertIn('storage', stop)
                self.assertIn(b'scenario-first-iteration', midpoint_logs[0],
                              'scenario marker was unavailable before process-group TERM')
                has_summary = (out/'k6-summary.json').is_file()
                if not launch:
                    self.assertFalse(has_summary)
                reduced = reduce_stage(out, d/'reduced')
                if not has_summary:
                    self.assertEqual(reduced['coverage']['http']['verdict'], 'UNMEASURED')
                self.assertEqual(reduced['midpointEvaluatorProgress']['verdict'], 'FAIL')
                early, = reduced['interruptedDrivers']
                self.assertNotEqual(early['returncode'], 0)
                self.assertEqual(early['summaryRetained'], has_summary)
                self.assertEqual(early['finalAccounting'], 'UNMEASURED')
                self.assertLessEqual(early['markersAtMs']['scenario-first-iteration'],
                                     reduced['midpointEvaluatorProgress']['observedAt'] * 1000)
                print('Strict midpoint refusal retained; stopped driver exit', early['returncode'],
                      f'with scenario marker; summary retained={has_summary}')
            else:
                from node_observation import log_events
                markers = log_events(events, names=('jwt-setup-start', 'jwt-setup-end', 'scenario-first-iteration'))
                midpoint = response['observedAt']
                signalled = float((out/'.window').read_text())
                self.assertLess(signalled, midpoint)
                self.assertGreaterEqual(midpoint - signalled, 1)
                self.assertLess(markers['jwt-setup-start'] / 1000, midpoint)
                self.assertLess(midpoint, markers['jwt-setup-end'] / 1000)
                self.assertLessEqual(markers['jwt-setup-end'], markers['scenario-first-iteration'])
                self.assertTrue((out/'k6-summary.json').is_file())
                self.assertNotIn(b'terminal stdout', events.read_bytes())
                self.assertFalse((out/'progress-midpoint-failure.json').exists())
                print(f'Delayed setup: midpoint +{midpoint-signalled:.3f}s from probe, '
                      f'first ordinary marker +{markers["scenario-first-iteration"]/1000-signalled:.3f}s')

    def test_reducer_keeps_only_markers_for_incomplete_configured_shard(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / 'load'
            stage.mkdir()
            k.write(stage/'k6-process-0.json', {'returncode':0})
            k.write(stage/'k6-summary-0.json', {'metrics':{}})
            k.write(stage/'k6-process-1.json', {'returncode':105})
            markers = {'driver-setup-start':1000, 'driver-setup-end':2000, 'driver-scenario-start':2100}
            log = stage/'k6-shard-1.log'
            with log.open('w') as stream:
                for event, at_ms in markers.items():
                    value = json.dumps({'event':event, 'atMs':at_ms, 'other':'private'})
                    stream.write('level=info msg=' + json.dumps(value) + ' source=console\n')
            result = reduce_stage(stage, stage.parent/'reduce')
            self.assertEqual(result['interruptedDrivers'], [{
                'process':'k6-process-1.json', 'returncode':105, 'markersAtMs':markers,
                'summaryRetained':False, 'finalAccounting':'UNMEASURED'
            }])
            self.assertEqual(result['coverage']['http']['verdict'], 'UNMEASURED')
            self.assertEqual(result['inputs'][str(log)], k.digest(log))

    def test_midpoint_failure_keeps_private_raw_and_partial_driver_evidence(self):
        self.trial(fail=True)

    def test_not_ready_midpoint_is_a_signal_and_driver_continues(self):
        self.trial(fail=False, signal=True)

    def test_healthy_midpoint_capture_runs_during_delayed_driver_setup(self):
        self.trial(fail=False)

    def test_omitted_drain_still_collects_red_then_restored(self):
        import types
        source = Path(execute.__file__).read_text()
        needle = "        if load:\n            # All-tenant fixed-floor catch-up"
        self.assertEqual(source.count(needle), 1)
        broken = types.ModuleType('missing_catchup')
        broken.__file__ = execute.__file__
        exec(compile(source.replace(needle, "        if load and 'drainSeconds' in settings:\n            # All-tenant fixed-floor catch-up"), execute.__file__, 'exec'), broken.__dict__)
        with self.assertRaises(AssertionError): self.trial(fail=False, module=broken)
        self.trial(fail=False)
        print('KUBERNETES_CATCHUP missing default selection RED; RESTORED_GREEN')
