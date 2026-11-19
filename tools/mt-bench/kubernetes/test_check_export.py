"""Held export projection uses the renderer's actual resource accounting mode."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import kube_adapter as k
import check_export
from test_adapter import fixture


class ExportProjection(unittest.TestCase):
    def test_explicit_request_accounting_projects_and_changed_packet_refuses(self):
        for mode in (None, 'limits-v1', 'requests-v1'):
            with self.subTest(mode=mode), TemporaryDirectory() as scratch:
                root = Path(scratch)
                export = root/'export'
                export.mkdir()
                config, inventory, rendered, _ = fixture()
                inventory.update(namespace=config['namespace'], ownership={'label': {config['ownerLabel']: config['runId']}},
                                 images={'app': config['pins']['appImage'], 'postgres': 'example.invalid/postgres@sha256:'+'9'*64},
                                 storage={'mode': 'disposable'}, workloads={
                                     obj['metadata']['name']: {'kind': obj['kind'], 'containers': [
                                         {'name': container['name'], 'init': False}
                                         for container in obj['spec']['template']['spec']['containers']]}
                                     for obj in rendered if obj['kind'] in k.WORKLOADS})
                if mode is not None:
                    inventory['resourceAccounting'] = mode
                (export/'package.tar').write_bytes(b'synthetic immutable archive')
                k.write(export/'fixture-inventory.json', inventory)
                k.write(export/'manifests.json', rendered)
                k.write(export/'package-receipt.json', {
                    'archiveSha256': k.digest(export/'package.tar'), 'bindingCommit': config['pins']['bindingCommit'],
                    'appSourceContract': {'coreCommit': config['pins']['pair']['core'],
                                          'deployCommit': config['pins']['pair']['deploy'],
                                          'localImageId': config['pins']['appImageId']}})
                result = check_export.check(export, root/'prepared')
                self.assertEqual((result['offlineBoundary'], result['runtimeStatus']), ('PASS', 'HELD'))
                held = k.document(root/'prepared/operator-inputs.held.json')
                self.assertEqual('resourceAccounting' in held, mode is not None)
                self.assertEqual(held.get('resourceAccounting', 'limits-v1'), mode or 'limits-v1')
                _, prepared, objects = k.load(root/'prepared/packet')
                if mode == 'requests-v1':
                    changed = copy.deepcopy(prepared)
                    changed['resourceAccounting'] = 'limits-v1'
                    with self.assertRaisesRegex(k.Refused, 'RESOURCE_ACCOUNTING_MISMATCH'):
                        k.validate(changed, inventory, rendered)
                    k.validate(prepared, inventory, rendered)


if __name__ == '__main__':
    unittest.main()
