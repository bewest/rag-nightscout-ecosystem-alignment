"""Exercise the owner-monitored local run boundary with inert host processes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import adapter
import runner
from test_run_configuration import config


class OwnerMonitoredRun(unittest.TestCase):
    def test_open_run_has_finite_phase_budgets_and_is_local_discovery_only(self):
        value = config()
        value['tier'] = 'discovery'
        value['workSeconds'] = None
        value['prepare'].pop('receipt')
        with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
            with self.assertRaisesRegex(RuntimeError, 'PHASE_BUDGETS_REQUIRED'):
                runner.tier_plan(value)
            value['prepare'].update({'setup-seconds': 900, 'drain-seconds': 600})
            plan = runner.tier_plan(value)
            self.assertEqual(plan['execution']['mode'], runner.TO_COMPLETION)
            self.assertIsNone(plan['execution']['workSeconds'])
            self.assertEqual(plan['effective']['cadence']['setupSeconds'], 900)
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                cfg = base / 'input.json'
                cfg.write_text(json.dumps(value))
                with patch.object(runner, 'arm_window') as effects:
                    with self.assertRaisesRegex(RuntimeError, 'TO_COMPLETION_REQUIRES_ONE_SHOT'):
                        runner.prepare(cfg, base/'run')
                    effects.assert_not_called()
            value['tier'] = 'smoke'
            with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_FINITE_LIMIT'):
                runner.validate_config(value)

    def test_owner_guard_waits_while_live_then_retains_aborted_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(15)'])
            try:
                controller, _ = runner.controller_identity(parent.pid)
                adapter.write(root/'execution.json', {'mode': runner.TO_COMPLETION, 'controller': controller,
                              'owner': 'synthetic', 'startedAt': 1, 'stopWorkAt': None, 'cleanupAt': None,
                              'cleanupSeconds': 30})
                adapter.write(root/'result.json', {'version': 1, 'status': 'PREPARED'})
                adapter.write(root/'phase.json', {'phase': 'run'})
                guard = subprocess.Popen([sys.executable, '-B', runner.__file__, '_guard', root])
                try:
                    deadline = time.monotonic() + 5
                    while not (root/'guard-ready.json').exists() and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue((root/'guard-ready.json').exists())
                    self.assertIsNone(guard.poll())
                    self.assertFalse((root/'cleanup.json').exists())
                    # An old wall-clock start has no effect while the recorded process is alive.
                    self.assertTrue(runner.work_active(adapter.document(root/'execution.json')))
                    parent.kill()
                    parent.wait(timeout=5)
                    self.assertEqual(guard.wait(timeout=5), 0)
                finally:
                    if guard.poll() is None:
                        guard.kill()
                        guard.wait(timeout=5)
                cleanup = adapter.document(root/'cleanup.json')
                result = adapter.document(root/'result.json')
                self.assertEqual(cleanup['reason'], 'CONTROLLER_EXITED')
                self.assertEqual(result['status'], 'ABORTED')
                self.assertEqual(result['phase'], 'run')
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=5)

    def test_stage_gate_prevents_effect_before_atomic_custody_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'entered'
            (root/'adapter.py').write_text('from pathlib import Path\nimport sys\nPath(sys.argv[1]).touch()\n')
            processes = []
            actual_popen = subprocess.Popen

            def register(*args, **kwargs):
                child = actual_popen(*args, **kwargs)
                processes.append(child)
                return child

            state = {'mode': runner.TO_COMPLETION, 'owner': 'synthetic'}
            with patch.object(runner, 'HERE', root), patch.object(runner.subprocess, 'Popen', side_effect=register):
                with patch.object(runner, 'write', side_effect=OSError('journal rejected')):
                    with open(os.devnull, 'wb') as log, self.assertRaisesRegex(OSError, 'journal rejected'):
                        runner.launch_stage(root, log, [str(output)], state)
                self.assertEqual(processes[-1].wait(timeout=5), 1)
                self.assertFalse(output.exists())
                with open(os.devnull, 'wb') as log:
                    child = runner.launch_stage(root, log, [str(output)], state)
                self.assertEqual(child.wait(timeout=5), 0)
                self.assertTrue(output.exists())
                self.assertEqual(adapter.document(root/'stage-job.json')['pid'], child.pid)
