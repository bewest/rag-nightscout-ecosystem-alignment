from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import api_warm_cause as warm


class WarmCauseMountTest(unittest.TestCase):
    def test_writable_capture_mount_uses_canonical_default(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'core' / warm.SOURCE
            source.parent.mkdir(parents=True)
            source.write_text('controlled startup source fixture\n')
            (root / 'state').mkdir()
            manifest = {'owner':'1'*32,'pair':{'core':'2'*40,'deploy':'3'*40},
                        'profile':'pgstream-sample','runPurpose':'discovery','tenants':10000}
            config = {'services':{'api':{'command':['node','deploy/multitenant/entrypoint.js','api']}}}
            warm.install(config,root,manifest,warm.MODE)
            writable, = (mount for mount in config['services']['api']['volumes']
                         if mount['target']==warm.OUT)
            self.assertNotIn('read_only',writable)
            broken = deepcopy(config)
            target, = (mount for mount in broken['services']['api']['volumes']
                       if mount['target']==warm.OUT)
            target['read_only'] = False
            with self.assertRaisesRegex(RuntimeError,'M7_API_WARM_MOUNT'):
                warm.verify(broken,root,manifest)
            warm.verify(config,root,manifest)


if __name__ == '__main__':
    unittest.main()
