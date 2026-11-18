import ast
import json
from pathlib import Path
import tempfile
import unittest


def control():
    path = Path(__file__).with_name('attach.py')
    functions = [node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)
                 and node.name == 'observe_selected_bootstrap']
    globals_ = {'read': lambda file: json.loads(file.read_text())}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), globals_)
    return globals_['observe_selected_bootstrap']


class BootstrapAttachment(unittest.TestCase):
    def test_selected_mode_drives_exact_pre_observation_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root/'packet'
            packet.mkdir()
            candidate = {'sourceAcceptance': 'PENDING'}
            readback = {'mode': 'embedded-image', 'effectiveInstanceAcceptance': 'PENDING'}
            calls = []
            step = control()

            def run():
                (packet/'run.json').write_text(json.dumps({'pins': {'candidate': candidate}}))
                (root/'bootstrap-helper-readback.json').write_text(json.dumps(readback))
                step(packet, root, 'namespace-uid', ['adapter'], lambda name, args: calls.append((name, args)))

            run()
            native = [(name, ['adapter', name, packet]) for name in ('observe', 'candidate-proof', 'policy')]
            self.assertEqual(calls, native)
            calls.clear()
            readback.update(mode='diagnostic-overlay', sha256='a'*64)
            with self.assertRaisesRegex(RuntimeError, 'BOOTSTRAP_HELPER_UNDECLARED'):
                run()
            self.assertEqual(calls, [])
            candidate['runtimeBootstrapHelper'] = {'sha256': 'b'*64}
            with self.assertRaisesRegex(RuntimeError, 'BOOTSTRAP_HELPER_MISSING_OR_CHANGED'):
                run()
            self.assertEqual(calls, [])
            readback['sha256'] = 'b'*64
            run()
            self.assertEqual(calls, [('bootstrap-map', ['adapter','bootstrap-map',packet,'namespace-uid']),
                                     *native])
            calls.clear()
            readback['effectiveInstanceAcceptance'] = 'PASS'
            with self.assertRaisesRegex(RuntimeError, 'BOOTSTRAP_ACCEPTANCE_CHANGED'):
                run()
            self.assertEqual(calls, [])
