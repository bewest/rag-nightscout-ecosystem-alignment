import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import point_results as points
import runner


class StandardPoint(unittest.TestCase):
    def test_public_compose_pre_entry_failure_and_collision(self):
        with TemporaryDirectory() as temp:
            case = Path(temp)/'point'
            with patch.object(sys, 'argv', ['runner.py', 'run', str(case/'missing.json'), str(case), '--standard-case']):
                with self.assertRaises(FileNotFoundError):
                    runner.main()
                self.assertEqual({p.name for p in case.iterdir()}, {'raw', 'result.json', 'cleanup.json'})
                self.assertEqual(points.read(case/'result.json')['status'], 'FAILED_PARTIAL')
                self.assertEqual(points.read(case/'cleanup.json')['status'], 'UNMEASURED')
                previously = (case/'result.json').read_bytes()
                with self.assertRaises(FileExistsError):
                    runner.main()
                self.assertEqual((case/'result.json').read_bytes(), previously)

    def test_failure_after_prepare_has_terminal_result(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/'point'
            def prepared(config, raw, one_shot):
                raw.mkdir()
                points.write(raw/'result.json', {'status':'PREPARED', 'phase':'prepare'})
                return raw
            with patch.object(sys, 'argv', ['runner.py', 'run', 'config', str(root), '--standard-case']), \
                 patch.object(runner, 'prepare', side_effect=prepared), \
                 patch.object(runner, 'execute', side_effect=RuntimeError('M7_RUNNER_WORK_DEADLINE')):
                with self.assertRaisesRegex(RuntimeError, 'WORK_DEADLINE'):
                    runner.main()
            self.assertEqual(points.read(root/'result.json')['status'], 'FAILED_PARTIAL')
            self.assertEqual(points.read(root/'result.json')['code'], 'M7_RUNNER_WORK_DEADLINE')

    def test_named_observation_memory_cleanup_and_missing_accounting(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/'raw'
            root.mkdir()
            value = points.publish_compose(root, {'memAvailableAtEntryBytes': 37}, {'status': 'DEFERRED_TO_SESSION_CLOSE'})
            self.assertEqual(value['memAvailableAtEntryBytes'], 37)
            self.assertEqual(value['measurements']['offeredWork'], 'UNMEASURED')
            self.assertEqual(value['cleanup']['status'], 'DEFERRED_TO_SESSION_CLOSE')
            self.assertFalse((root.parent/'result.json').exists())

    def test_native_failure_and_unconfirmed_host_unit(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/'point'
            case = root/'raw'/'point'
            runtime = case/'runtime'
            runtime.mkdir(parents=True)
            for name, value in [('first-failure', {'code': 'K8S_FAIL'}), ('absence', {'absent': True}),
                                ('native-unit', {'unit': 'ns-point-native.scope'})]:
                points.write(runtime/(name+'.json'), value)
            points.publish_native(case)
            self.assertEqual(points.read(root/'result.json')['firstFailure']['code'], 'K8S_FAIL')
            self.assertEqual(points.read(root/'cleanup.json')['status'], 'UNMEASURED')
            self.assertEqual(set(p.name for p in root.iterdir()), {'raw', 'cleanup.json', 'result.json'})
            with self.assertRaises(FileExistsError):
                points.publish_native(case)
