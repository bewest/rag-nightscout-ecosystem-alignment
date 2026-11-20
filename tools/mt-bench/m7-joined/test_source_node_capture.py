"""Source helper failures retain private evidence without changing public errors."""
from contextlib import ExitStack
import inspect
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import adapter as a


class SourceNodeCapture(unittest.TestCase):
    def fail(self, argv, **kwargs):
        code = "const fs=require('node:fs');fs.writeSync(1,'o'.repeat(300000));fs.writeSync(2,'e'.repeat(300000)+'\\nM7_SAFE_SOURCE_REFUSAL\\nprivate-synthetic-value');process.exit(7);"
        return a._command([str(Path(shutil.which('node')).resolve()), '-e', code], phase=kwargs.get('phase'))

    def call(self, root, phase, contract=None):
        a.write(root / 'frozen.compose.json', {})
        with ExitStack() as stack:
            stack.enter_context(patch.object(a.static_topology, 'state_documents', return_value={}))
            stack.enter_context(patch.object(a.static_topology, 'verify_documents', return_value={'status': 'VERIFIED'}))
            return (contract or a.static_runtime_contract)(root, {})

    def criterion(self, root, phase, contract=None):
        root.mkdir()
        with patch.object(a, 'command', side_effect=self.fail):
            with self.assertRaisesRegex(RuntimeError, 'M7_COMMAND_FAILED:') as failure:
                self.call(root, phase, contract)
        self.assertNotIn('private-synthetic-value', str(failure.exception))
        files = list((root / 'source-node-checks' / phase).glob('*/*.json'))
        if len(files) != 1:
            raise AssertionError('SOURCE_NODE_FAILURE_MUST_BE_RETAINED')
        record = json.loads(files[0].read_text())
        self.assertEqual(record['phase'], phase);self.assertEqual(record['returncode'], 7)
        self.assertEqual(record['failureType'], 'RuntimeError')
        for stream in ('stdout', 'stderr'):
            file = files[0].parent / record[stream]
            counts = record['outputRetention']['streams'][stream]
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(file.stat().st_size, counts['retainedBytes'])
            self.assertLessEqual(file.stat().st_size, 262144)
            self.assertTrue(counts['truncated'])
            self.assertGreater(counts['observedBytes'], counts['retainedBytes'])
        self.assertIn(b'M7_SAFE_SOURCE_REFUSAL', (files[0].parent / record['stderr']).read_bytes())
        self.assertEqual(files[0].parent.stat().st_mode & 0o777, 0o700)

    def test_actual_source_plan_call_boundary_retains_private_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            for phase in ('static-runtime-plan',):
                self.criterion(Path(temporary) / phase, phase)

    def test_normal_source_helper_json_is_unchanged_and_capture_is_complete(self):
        def success(argv, **kwargs):
            return a._command([str(Path(shutil.which('node')).resolve()), '-e', "console.log(JSON.stringify({ok:true,schema:1}))"], phase=kwargs.get('phase'))
        with tempfile.TemporaryDirectory() as temporary:
            for phase in ('static-runtime-plan',):
                root = Path(temporary) / phase;root.mkdir()
                with patch.object(a, 'command', side_effect=success):
                    value = self.call(root, phase)
                self.assertEqual(value['status'], 'VERIFIED')
                record = json.loads(next((root / 'source-node-checks' / phase).glob('*/*.json')).read_text())
                self.assertEqual(record['returncode'], 0);self.assertIsNone(record['failureType'])
                self.assertTrue(all(not row['truncated'] for row in record['outputRetention']['streams'].values()))

    def test_removed_capture_is_red_and_restored(self):
        source = inspect.getsource(a.static_runtime_contract)
        broken = source.replace("with private_commands(d/'source-node-checks'/'static-runtime-plan'/uuid.uuid4().hex, max_output_bytes=262144):", 'with contextlib.nullcontext():')
        self.assertNotEqual(source, broken)
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(a, 'command', side_effect=self.fail):
                scope = dict(vars(a));exec(compile(broken, 'source_capture_control', 'exec'), scope)
            self.criterion(Path(temporary) / 'normal', 'static-runtime-plan')
            with self.assertRaisesRegex(AssertionError, 'SOURCE_NODE_FAILURE_MUST_BE_RETAINED'):
                self.criterion(Path(temporary) / 'removed', 'static-runtime-plan', scope['static_runtime_contract'])
            self.criterion(Path(temporary) / 'restored', 'static-runtime-plan')

    def test_timeout_retains_bounded_tail_and_successful_truncation_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with a.private_commands(root / 'timeout', max_output_bytes=64):
                with self.assertRaises(subprocess.TimeoutExpired):
                    a._command([sys.executable, '-c', "import os,time;os.write(2,b'x'*200+b'M7_SAFE_TIMEOUT');time.sleep(1)"], timeout=.1, phase='static-runtime-plan')
            record = json.loads(next((root / 'timeout').glob('*.json')).read_text())
            self.assertEqual(record['failureType'], 'TimeoutExpired')
            self.assertEqual(record['outputRetention']['streams']['stderr']['retainedBytes'], 64)
            self.assertIn(b'M7_SAFE_TIMEOUT', (root / 'timeout' / record['stderr']).read_bytes())
            with a.private_commands(root / 'success', max_output_bytes=64):
                with self.assertRaisesRegex(RuntimeError, 'M7_PRIVATE_OUTPUT_TRUNCATED'):
                    a._command([sys.executable, '-c', "print('x'*100)"], phase='static-runtime-plan')
            with a.private_commands(root / 'restored', max_output_bytes=64):
                self.assertEqual(a._command([sys.executable, '-c', "print('ok')"]), 'ok\n')

    def test_invalid_retention_bound_refuses_before_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            for value in (0, -1, True, 1048577):
                root = Path(temporary) / str(value)
                with self.assertRaisesRegex(RuntimeError, 'M7_PRIVATE_CAPTURE_LIMIT'):
                    with a.private_commands(root, max_output_bytes=value):
                        self.fail('unused')
                self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
