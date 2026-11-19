"""simple-run-cleanup (Compose): one `down -v` on the owned project, then one absence check."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adapter as a

PROJECT = 'ns-simple-cleanup-fixture'


class Docker:
    """Records docker calls; `left` is the set of resource kinds still labelled after down."""
    def __init__(self, left=()):
        self.left, self.calls = set(left), []
    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        label = 'label=com.docker.compose.project=' + PROJECT
        if argv[:2] == ['docker', 'ps']:
            assert label in argv, 'absence check must filter on the owned project label'
            return 'abc123\n' if 'container' in self.left else ''
        if argv[:2] == ['docker', 'inspect']:
            return json.dumps([{'Id': 'abc123', 'Config': {'Labels': {}}}])
        if argv[:2] in (['docker', 'network'], ['docker', 'volume']):
            assert label in argv
            return 'id1\n' if argv[1] in self.left else ''
        raise AssertionError(argv)


class SimpleCleanup(unittest.TestCase):
    def absence(self, left):
        with patch.object(a, 'command', Docker(left)):
            return a.assert_absent({'project': PROJECT})

    def test_nothing_left_is_absent(self):
        self.assertEqual(self.absence(())['status'], 'ABSENT')

    def test_a_leftover_labelled_resource_is_found_and_fails(self):
        for kind, code in (('container', 'CONTAINER_REMAINS'), ('network', 'NETWORK_REMAINS'), ('volume', 'VOLUME_REMAINS')):
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, code):
                self.absence({kind})

    def test_down_is_compose_down_volumes_and_one_absence_check_with_no_census_or_per_resource_delete(self):
        docker = Docker()
        with tempfile.TemporaryDirectory() as area, patch.object(a, 'command', docker), \
             patch.object(a, 'compose') as compose, patch.object(a, 'terminal_snapshot'), \
             patch.object(a.profile_provenance, 'capture_logs', return_value={'version': 1}), \
             patch.object(a, 'document', return_value={'services': {}}):
            d = Path(area)
            (d/'role-logs').mkdir()
            a._down(d, {'project': PROJECT, 'prepared': True, 'owner': 'o'*32, 'core': None, 'coreRepository': '.', 'pair': {'core': 'x'}})
        compose.assert_called_once()
        self.assertEqual(compose.call_args.args[1:5], ('--profile', 'ops', 'down', '--volumes'))
        self.assertFalse([c for c in docker.calls if c[:2] in (['docker', 'rm'], ['docker', 'inspect'])],
                         'no container census or per-resource removal')
        self.assertEqual(sorted(c[1] for c in docker.calls), ['network', 'ps', 'volume'])


if __name__ == '__main__':
    unittest.main()
