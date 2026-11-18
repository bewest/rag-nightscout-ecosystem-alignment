import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_adapter import k as adapter, execute


class AccessDiagnostics(unittest.TestCase):
    def test_socket_warmup_failure_retains_original_refusal_and_bounded_prior_witness(self):
        code = 'K8S_SOCKET_PREWARM_UNMEASURED'
        before = {'tenantIndex': 0, 'attempts': 1, 'refused403': 0, 'elapsedMs': 8, 'verdict': 'CONNECTED'}
        row = {'tenantIndex': 1, 'stage': 'warmup', 'engineOpened': False, 'elapsedMs': 6000,
               'firstError': {'errorClass': 'TransportError', 'status': 403, 'code': None},
               'attempts': 4, 'refused403': 4, 'prior': [before]}
        payload = {'socketEvidence': row}
        self.assertEqual(execute.socket_failure(code, json.dumps(payload).encode()), payload)
        before['credential'] = 'private marker'
        self.assertEqual(execute.socket_failure(code, json.dumps(payload).encode()), {})

    def test_spawned_socket_refusal_retains_only_eligible_transport_fields(self):
        sample = {'socketEvidence': {'tenantIndex': 0, 'stage': 'connect', 'engineOpened': False, 'elapsedMs': 5000,
                                     'firstError': {'errorClass': 'TransportError', 'status': 502, 'code': None}}}
        code = 'K8S_SOCKET_REFUSAL_UNMEASURED'
        def invoke(value):
            stdout = json.dumps(value)
            script = f'import sys; print({stdout!r}); print({code!r}, file=sys.stderr); sys.exit(1)'
            captured = {}
            with patch.object(adapter, 'deadline', return_value=5), self.assertRaisesRegex(adapter.Refused, code):
                execute.finite({}, [sys.executable, '-B', '-c', script], seconds=5,
                               failure_stdout=lambda name, raw: captured.update(execute.socket_failure(name, raw)))
            return captured
        self.assertEqual(invoke(sample), sample)
        sample['socketEvidence']['firstError']['message'] = 'private marker'
        self.assertEqual(invoke(sample), {})

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

            def run_witness(*_, **kwargs):
                steps.append('witness')
                return b'{"verdict":"PASS","tenantRosterSize":2,"witnessTenants":["first","last"]}'

            with patch.object(adapter.candidate, 'require'), \
                 patch.object(adapter, 'active_baseline', return_value=baseline), \
                 patch.object(execute, 'roster', return_value=roster), \
                 patch.object(execute, 'actor', side_effect=lambda _: steps.append('actor')), \
                 patch.object(execute, 'environment', return_value={}), \
                 patch.object(adapter, 'observe', side_effect=observe), \
                 patch.object(execute, 'finite', side_effect=run_witness):
                result = execute.access(root, c, {}, object())
            self.assertEqual(steps, ['observe', 'actor', 'witness', 'observe'])
            self.assertEqual(result['namespaceUid'], 'owned')
