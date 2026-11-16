import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import dependency_reuse as reuse

NODE = '/home/bewest/n/n/versions/node/24.22.1/bin/node'
NPM = '/home/bewest/n/n/versions/node/24.22.1/lib/node_modules/npm/bin/npm-cli.js'


class Reuse(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'qualified'
        self.source.mkdir()
        self.calls = []
        self.tools = {}
        for name, path in [('node', NODE), ('npm', NPM)]:
            argv = [NODE, '--version'] if name == 'node' else [NODE, NPM, '--version']
            self.tools[name] = {'path': path, 'sha256': reuse.file_sha(path),
                                'version': subprocess.check_output(argv, text=True).strip()}
        modules = {}
        packages = {'': {'name': 'synthetic-fixture', 'version': '1.0.0'}}
        exports = {'socket.io-client': 'exports.io=()=>{};', 'pg': 'exports.Pool=function(){};exports.Client=function(){};', 'js-yaml': 'exports.load=()=>{};'}
        for name in reuse.MODULES:
            root = self.source / 'node_modules' / name
            root.mkdir(parents=True)
            (root / 'package.json').write_text(json.dumps({'name': name, 'version': '1.0.0', 'main': 'index.js'}))
            (root / 'index.js').write_text(exports[name])
            packages['node_modules/' + name] = {'version': '1.0.0'}
            modules[name] = {'entry': str(root / 'index.js'), 'entrySha256': reuse.file_sha(root / 'index.js'), 'version': '1.0.0'}
        self.package = json.dumps({'name': 'synthetic-fixture', 'version': '1.0.0'}).encode()
        self.lock = json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()
        (self.source / 'package.json').write_bytes(self.package)
        (self.source / 'package-lock.json').write_bytes(self.lock)
        receipt = {'kind': 'owned-lockfile-install', 'tools': self.tools,
                   'packageSha256': reuse.sha(self.package), 'lockSha256': reuse.sha(self.lock),
                   'contexts': {'generator': {'root': str(self.source), 'dependencyRoot': str(self.source / 'node_modules'),
                     'nodeBinary': NODE, 'nodeVersion': self.tools['node']['version'], 'modules': modules}}}
        self.receipt = self.base / 'qualified-receipt.json'
        self.receipt.write_text(json.dumps(receipt))

    def run_command(self, argv):
        self.calls.append(argv)
        self.assertEqual(argv[0], NODE)
        self.assertNotIn('ci', argv)
        self.assertNotIn('install', argv)
        return subprocess.check_output(argv, env={'PATH': str(Path(NODE).parent), 'LANG': 'C'}, text=True, timeout=10)

    def qualify(self, **overrides):
        args = dict(source=self.source, receipt_path=self.receipt,
                    receipt_sha256=reuse.file_sha(self.receipt), package_bytes=self.package,
                    lock_bytes=self.lock, tools=self.tools, run=self.run_command)
        args.update(overrides)
        return reuse.preflight(**args)

    def test_actual_node_qualified_copy_and_unchanged_source(self):
        q = self.qualify()
        before = reuse.tree(self.source / 'node_modules')
        target = self.base / 'owned'
        result = reuse.copy_owned(destination=target, qualification=q, package_bytes=self.package,
                                  lock_bytes=self.lock, run=self.run_command)
        self.assertEqual(result['network'], 'NOT_USED')
        self.assertEqual(reuse.tree(target / 'node_modules'), before)
        self.assertEqual(reuse.tree(self.source / 'node_modules'), before)
        self.assertFalse((target / 'node_modules').is_symlink())
        (target / 'node_modules/pg/index.js').write_text('own mutation')
        self.assertEqual(reuse.tree(self.source / 'node_modules'), before)

    def test_wrong_source_or_receipt_or_tool_refuses_before_effect(self):
        for change in [{'package_bytes': b'wrong'}, {'receipt_sha256': '0' * 64},
                       {'tools': {**self.tools, 'node': {**self.tools['node'], 'sha256': '0' * 64}}}]:
            with self.subTest(change=change):
                self.calls.clear()
                with self.assertRaises(RuntimeError):
                    self.qualify(**change)
                self.assertEqual(self.calls, [])
                self.assertFalse((self.base / 'owned').exists())

    def test_incomplete_and_changed_entry_refuse_before_node(self):
        entry = self.source / 'node_modules/pg/index.js'
        entry.write_text('throw Error("must not execute")')
        with self.assertRaisesRegex(RuntimeError, 'MODULE_FINGERPRINT'):
            self.qualify()
        self.assertEqual(self.calls, [])
        (self.source / 'node_modules/pg/package.json').unlink()
        with self.assertRaisesRegex(RuntimeError, 'INCOMPLETE'):
            self.qualify()

    def test_escape_link_refuses_before_node(self):
        (self.source / 'node_modules/escape').symlink_to('/tmp')
        with self.assertRaisesRegex(RuntimeError, 'LINK_ESCAPE'):
            self.qualify()
        self.assertEqual(self.calls, [])

    def test_changed_preflight_tree_and_platform_refuse_before_target(self):
        q = self.qualify()
        (self.source / 'node_modules/extra.txt').write_text('changed after seal')
        target = self.base / 'owned'
        with self.assertRaisesRegex(RuntimeError, 'QUALIFICATION_CHANGED'):
            reuse.copy_owned(destination=target, qualification=q, package_bytes=self.package,
                             lock_bytes=self.lock, run=self.run_command)
        self.assertFalse(target.exists())
        q = self.qualify()
        q['platform']['nodeABI'] = 'foreign'
        with self.assertRaisesRegex(RuntimeError, 'QUALIFICATION_CHANGED'):
            reuse.copy_owned(destination=target, qualification=q, package_bytes=self.package,
                             lock_bytes=self.lock, run=self.run_command)
        self.assertFalse(target.exists())

    def test_explicit_retained_preparation_chain_and_wrong_head(self):
        alternate = self.base / 'retained-baseline'
        reuse.shutil.copytree(self.source, alternate, symlinks=True)
        installed = alternate / 'node_modules/.package-lock.json'
        installed.write_text('{}')
        receipt = self.base / 'source-preparation.json'
        receipt.write_text(json.dumps({
            'status': 'OWN_SOURCE_DEPENDENCY_AND_POSTINSTALL_PREPARATION_PASS_NO_NATIVE',
            'sourceTree': str(alternate), 'sourceHead': 'a' * 40,
            'packageSha256': reuse.sha(self.package), 'lockSha256': reuse.sha(self.lock),
            'realCopiedDependencyTree': True, 'nestedRootNodeModulesAbsent': True,
            'absoluteLinks': [], 'brokenLinks': [],
            'postinstall': {'exit': 0, 'command': [NODE, 'bin/postinstall.js']},
            'dependencyInstalledLockSha256': reuse.file_sha(installed)}))
        selected = {'path': str(receipt), 'sha256': reuse.file_sha(receipt), 'head': 'a' * 40}
        q = self.qualify(source=alternate, source_preparation=selected)
        self.assertEqual(q['source'], str(alternate))
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_PREPARATION'):
            self.qualify(source=alternate, source_preparation={**selected, 'head': 'b' * 40})
        self.assertEqual(self.calls, [])
        target = self.base / 'owned'
        reuse.copy_owned(destination=target, qualification=q, package_bytes=self.package,
                         lock_bytes=self.lock, run=self.run_command)
        self.assertTrue((target / 'dependency-reuse-ready.json').exists())

    def test_copy_corruption_refuses_without_ready(self):
        q = self.qualify()
        original = reuse.shutil.copytree
        def corrupt(source, destination, **kwargs):
            with patch.object(reuse.shutil, 'copytree', original):
                result = original(source, destination, **kwargs)
            (Path(destination) / 'pg/index.js').write_text('corrupt copy')
            return result
        target = self.base / 'owned'
        with patch.object(reuse.shutil, 'copytree', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'COPY_CHANGED'):
                reuse.copy_owned(destination=target, qualification=q, package_bytes=self.package,
                                 lock_bytes=self.lock, run=self.run_command)
        self.assertFalse((target / 'dependency-reuse-ready.json').exists())


if __name__ == '__main__':
    unittest.main()
