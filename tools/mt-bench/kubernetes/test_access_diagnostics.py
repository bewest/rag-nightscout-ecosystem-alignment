import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_adapter import k as adapter, execute


class AccessDiagnostics(unittest.TestCase):
    def test_retains_fixed_phase_type_and_source_frames_without_input_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            c = {'driver': {'node': 'synthetic', 'dependencies': 'private'},
                 'tenantsFile': 'private', 'baseUrl': 'synthetic', 'pins': {}, 'context': 'scope'}
            roster = [{'id': 'first'}, {'id': 'last'}]
            baseline = {'namespace': {'uid': 'owned'}}
            steps = []

            def observe(*_):
                steps.append('observe')

            with patch.object(adapter.candidate, 'require'), \
                 patch.object(adapter, 'active_baseline', return_value=baseline), \
                 patch.object(execute, 'roster', return_value=roster), \
                 patch.object(execute, 'actor', side_effect=lambda _: steps.append('actor')), \
                 patch.object(execute, 'environment', return_value={}), \
                 patch.object(adapter, 'observe', side_effect=KeyError('PRIVATE_INPUT_MARKER')), \
                 patch.object(execute, 'finite') as witness:
                with self.assertRaises(KeyError):
                    execute.access(root, c, {}, object())
                witness.assert_not_called()
            failure = json.loads((root/'access-failure.json').read_text())
            self.assertEqual(failure['phase'], 'before-observe')
            self.assertEqual(failure['errorType'], 'KeyError')
            self.assertIn('access', {row['function'] for row in failure['frames']})
            self.assertNotIn('PRIVATE_INPUT_MARKER', json.dumps(failure))
            self.assertFalse((root/'access.json').exists())
            (root/'access-failure.json').unlink()

            def run_witness(config, argv, **kwargs):
                self.assertEqual(argv[-1], c['driver']['dependencies'])
                steps.append('witness')
                return b'{"verdict":"PASS","tenantRosterSize":2,"witnessTenants":["first","last"]}'

            with patch.object(adapter.candidate, 'require'), \
                 patch.object(adapter, 'active_baseline', return_value=baseline), \
                 patch.object(execute, 'roster', return_value=roster), \
                 patch.object(execute, 'actor', side_effect=lambda _: steps.append('actor')), \
                 patch.object(execute, 'environment', return_value={}), \
                 patch.object(adapter, 'observe', side_effect=observe), \
                 patch.object(execute, 'finite', side_effect=run_witness):
                result = execute.access(root, {**c, 'accessSetupSeconds': 60}, {}, object())
            self.assertEqual(steps, ['observe', 'actor', 'witness', 'observe'])
            self.assertEqual(result['namespaceUid'], 'owned')
