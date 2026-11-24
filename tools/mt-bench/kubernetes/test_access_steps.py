import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import execute


class AccessSteps(unittest.TestCase):
    """Round 2: the access witness appends per-step timings to D/access-steps.jsonl as it goes; a failure (including a
    kill at the 60 s bound) keeps them and names the last step in access-failure.json."""

    def test_failure_keeps_completed_steps_and_the_open_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            seen = {}

            def fake_finite(c, argv, *, env=None, seconds=120, **kw):
                seen['env'], seen['seconds'] = env, seconds
                path = Path(env['K8S_ACCESS_STEPS'])
                with path.open('a') as f:
                    f.write(json.dumps({'step': 'exchange', 'tenantIndex': 0, 'phase': 'start', 'at': 1}) + '\n')
                    f.write(json.dumps({'step': 'exchange', 'tenantIndex': 0, 'phase': 'end', 'at': 2, 'ms': 1, 'outcome': 'status-200'}) + '\n')
                    f.write(json.dumps({'step': 'cross-token-host', 'tenantIndex': 0, 'phase': 'start', 'at': 3}) + '\n')
                raise execute.k.Refused('K8S_ACCESS_TIMEOUT', 'FAIL')

            c = {'driver': {'node': 'node', 'dependencies': '/deps'}, 'tenantsFile': '/t', 'baseUrl': 'http://127.0.0.1:1'}
            with mock.patch.object(execute, 'roster', return_value=[{'id': 'a'}, {'id': 'b'}]), \
                    mock.patch.object(execute.k, 'active_baseline', return_value={}), \
                    mock.patch.object(execute.k, 'observe', return_value={}), \
                    mock.patch.object(execute, 'actor', return_value={}), \
                    mock.patch.object(execute, 'environment', return_value={}), \
                    mock.patch.object(execute, 'finite', side_effect=fake_finite):
                with self.assertRaises(execute.k.Refused):
                    execute.access(d, c, None, None)
            self.assertEqual(seen['seconds'], 60)
            self.assertEqual(seen['env']['K8S_ACCESS_STEPS'], str(d / 'access-steps.jsonl'))
            failure = json.loads((d / 'access-failure.json').read_text())
            self.assertEqual(failure['steps']['completed'], 1)
            self.assertEqual(failure['steps']['open'], {'step': 'cross-token-host', 'tenantIndex': 0, 'at': 3})
            self.assertEqual(len((d / 'access-steps.jsonl').read_text().splitlines()), 3)


if __name__ == '__main__':
    unittest.main()
