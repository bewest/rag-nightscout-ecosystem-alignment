"""Compose commissioning stages and the shared monotonic stall window."""
import contextlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import adapter
from primer_progress import ComposePrimerWait, ProgressWindow


class PrimerProgress(unittest.TestCase):
    def test_work_extends_the_stall_window_only_before_expiry(self):
        at = 0
        window = ProgressWindow(10, now=lambda: at, completed=3)
        for at, count in [(8, 4), (16, 5), (24, 6)]:
            self.assertTrue(window.observe(count))
            self.assertEqual(window.remaining(), 10)
        for at, count in [(28, 6), (30, 3), (33, True)]:
            self.assertFalse(window.observe(count))
            self.assertEqual(window.remaining(), 34-at)
        at = 34
        self.assertEqual(window.remaining(), 0)
        self.assertFalse(window.observe(7))
        self.assertEqual(window.completed, 6)

    def test_attached_child_advances_past_former_cutoff_and_retry_only_times_out(self):
        # A real attached process publishes atomic checkpoint replacements. Both
        # stages run against the actual host waiter and its ordinary command path.
        child_source = """
import json, os, sys, time
from pathlib import Path
state, operation, mode = sys.argv[1:]
path = Path(state) / ('provisioned.json' if operation == 'provision' else 'tenants.json')
for count in range(1, 6):
    if mode == 'retry':
        print('alive and retrying', flush=True)
    rows = [{'id': str(i)} for i in range(count if mode == 'advance' else 1)]
    with path.with_suffix('.new').open('w') as stream:
        json.dump(rows if operation == 'provision' else {'tenants': rows}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(path.with_suffix('.new'), path)
    time.sleep(0.4)
"""
        for operation in ('provision', 'prime'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for mode in ('advance', 'retry'):
                    receipt = {}
                    if mode == 'retry':
                        # A finished tenant in a prior run is a baseline.
                        rows = [{'id': '0'}]
                        name = 'provisioned.json' if operation == 'provision' else 'tenants.json'
                        adapter.write(root/name, rows if operation == 'provision' else {'tenants': rows})
                    wait = ComposePrimerWait(root, operation, 1, receipt)
                    argv = [sys.executable, '-c', child_source, root, operation, mode]
                    started = time.monotonic()
                    with (root/'phase.log').open('wb') as log:
                        if mode == 'advance':
                            adapter.command(argv, file=log, wait_for_primer=wait)
                            self.assertEqual(receipt['completedTenants'], 5)
                            self.assertGreater(time.monotonic()-started, 1)
                        else:
                            with self.assertRaisesRegex(RuntimeError, 'M7_PRIMER_STALLED'):
                                adapter.command(argv, file=log, wait_for_primer=wait)
                            self.assertEqual(receipt['completedTenants'], 1)
                            self.assertIn('alive and retrying', (root/'phase.log').read_text())

    def test_outer_deadline_stops_a_live_child_before_its_stall_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = {}
            wait = ComposePrimerWait(root, 'prime', 60, stage)
            with (root/'phase.log').open('wb') as log, adapter.private_commands(root/'private'):
                with adapter.command_deadline(time.time()+0.2), self.assertRaises(subprocess.TimeoutExpired):
                    adapter.command([sys.executable, '-c', 'import time; time.sleep(20)'],
                                    file=log, wait_for_primer=wait)
            self.assertEqual(stage['completedTenants'], 0)
            self.assertGreater(wait.window.remaining(), 50)

    def test_role_milestones_keep_real_wait_alive_and_stalled_role_refuses(self):
        roles = ['api','evaluator']
        for advance in (False, True):
            with self.subTest(advance=advance), tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);stage={};start=time.monotonic()
                def ps(*argv, **kwargs):
                    self.assertEqual(argv[-2:],tuple(roles))
                    index=int((time.monotonic()-start)/0.20) if advance else 0
                    api=('running' if index>0 else 'created','healthy' if index>1 else '')
                    other=('running' if index>2 else 'created','healthy' if index>3 else '')
                    return 'api|%s|%s\nevaluator|%s|%s\n'%(*api,*other)
                wait=adapter.ComposeProgressWait(0.55,'M7_ROLE_READINESS_STALLED',
                    lambda:adapter.compose_role_progress(d,roles,stage,0.55))
                with patch.object(adapter,'compose',side_effect=ps), (d/'up.log').open('wb') as log:
                    child=[sys.executable,'-c','import time;time.sleep(1.0)']
                    if advance:
                        adapter.command(child,file=log,wait_for_primer=wait)
                        self.assertEqual(stage['roleProgress'],{'api':3,'evaluator':3})
                    else:
                        with self.assertRaisesRegex(RuntimeError,'M7_ROLE_READINESS_STALLED'):
                            adapter.command(child,file=log,wait_for_primer=wait)
                        self.assertLess(time.monotonic()-start,1.0)

    def test_compose_runner_uses_stage_seconds_as_inactivity_with_outer_work_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            services = {'primer': {'image': 'synthetic'}}
            adapter.write(root/'frozen.compose.json', {'services': services})
            manifest = {'generator': {'servingImageId': 'synthetic'}, 'tenants': 4,
                        'cadence': {'startupWindows': {'stageSeconds': 15}}}
            adapter.write(root/'state/primer/tenants.json', {'tenants': [{'id': 'existing'}]})
            plan = [('prime', 'compose', [])]
            def compose(*args, **kwargs):
                self.assertGreater(kwargs['timeout'], 100)
                self.assertLessEqual(kwargs['timeout'], 120)
                self.assertEqual(adapter.document(root/'frozen.compose.json')['services']['primer']['environment']['NS_PRIMER_STALL_SECONDS'], '15')
                self.assertTrue(callable(kwargs['wait_for_primer']))
                raise RuntimeError('M7_CONTROL_STOP')
            with contextlib.ExitStack() as stack:
                for name in ('frozen', 'experiment_host', 'verify', 'verify_generator', 'pin_service_images'):
                    stack.enter_context(patch.object(adapter, name))
                stack.enter_context(patch.object(adapter, 'deployment_plan', return_value=plan))
                stack.enter_context(patch.object(adapter, 'image', return_value='synthetic'))
                stack.enter_context(patch.object(adapter, 'compose', side_effect=compose))
                stack.enter_context(adapter.command_deadline(adapter.time.time()+120))
                with self.assertRaisesRegex(RuntimeError, 'M7_CONTROL_STOP'):
                    adapter.deploy(root, manifest)
            record, = adapter.document(root/'deployment-stages.json')
            self.assertEqual(record['primerStallSeconds'], 15)
            self.assertEqual(record['completedTenants'], 1)
