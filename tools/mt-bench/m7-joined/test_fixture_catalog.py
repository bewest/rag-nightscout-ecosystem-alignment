"""Fixture key and local catalog: a hit restores, a miss builds then registers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import fixture_catalog as fc

APP, PG = 'sha256:' + 'a'*64, 'sha256:' + 'b'*64
SCHEMA = 'migrations-tree:' + 'c'*40


def key(**changes):
    return fc.key(**{'tenants': 8, 'image': APP, 'postgres_image': PG, 'schema': SCHEMA, **changes})


class Key(unittest.TestCase):
    def test_every_field_changes_the_digest(self):
        base = fc.digest(key())
        for change in ({'tenants': 9}, {'image': 'sha256:' + 'd'*64}, {'postgres_image': 'sha256:' + 'e'*64},
                       {'schema': 'migrations-tree:' + 'f'*40}, {'transport': 'writer-driven'}, {'seed': 'other'},
                       {'evaluator_slices': 2}, {'history': {'mode': 'synthetic-sgv-6h-v1', 'anchorMs': 1}}):
            self.assertNotEqual(fc.digest(key(**change)), base, change)
        self.assertEqual(fc.digest(key()), base)

    def test_the_ordinary_seed_history_is_no_history(self):
        ordinary = {'additionalSeedRows': 0, 'mode': 'existing-provisioner-only', 'retention': 'UNMEASURED'}
        self.assertEqual(key(history=ordinary), key())

    def test_evaluator_k_leaves_the_key_only_for_a_k_free_transport(self):
        self.assertEqual(key(transport='writer-driven')['evaluatorSlices'], 1)
        with mock.patch.object(fc, 'K_FREE_TRANSPORTS', frozenset({'writer-driven'})):
            self.assertNotIn('evaluatorSlices', key(transport='writer-driven'))
            self.assertEqual(key(transport='writer-driven', evaluator_slices=3), key(transport='writer-driven'))
            self.assertIn('evaluatorSlices', key())

    def test_malformed_inputs_refuse(self):
        for change in ({'tenants': 0}, {'image': 'registry/app:tag'}, {'transport': 'mongo'}, {'seed': '/abs/dir'},
                       {'schema': 'abc'}, {'evaluator_slices': 0}):
            with self.assertRaises(fc.Refused):
                key(**change)

    def test_schema_is_the_migrations_tree_at_the_image_commit(self):
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo)
        git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        (repo/'migrations').mkdir()
        (repo/'migrations/a.json').write_text('{}')
        (repo/'README').write_text('x')
        git('add', '.'); git('-c', 'user.name=t', '-c', 'user.email=t@example.test', 'commit', '-qm', 'one')
        first = git('rev-parse', 'HEAD')
        (repo/'README').write_text('y')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.test', 'commit', '-qam', 'docs only')
        docs = git('rev-parse', 'HEAD')
        (repo/'migrations/a.json').write_text('{"v":2}')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.test', 'commit', '-qam', 'schema')
        self.assertEqual(fc.schema(repo, first), fc.schema(repo, docs))
        self.assertNotEqual(fc.schema(repo, first), fc.schema(repo, git('rev-parse', 'HEAD')))


class CatalogFile(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.catalog = fc.Catalog(self.root/'catalog.json')

    def built(self, value, platform='kubernetes'):
        directory = self.catalog.reserve(value, platform)
        directory.mkdir(mode=0o700)
        return self.catalog.register(value, platform, {'id': directory.name})

    def test_miss_build_register_then_hit_on_that_platform_only(self):
        self.assertIsNone(self.catalog.lookup(key(), 'kubernetes'))
        record = self.built(key())
        self.assertEqual(self.catalog.lookup(key(), 'kubernetes')['directory'], record['directory'])
        self.assertIsNone(self.catalog.lookup(key(), 'compose'))
        self.assertIsNone(self.catalog.lookup(key(tenants=9), 'kubernetes'))
        self.assertEqual(self.catalog.path.stat().st_mode & 0o777, 0o600)

    def test_a_building_record_is_not_a_hit_and_refuses_a_second_live_builder(self):
        self.catalog.reserve(key(), 'kubernetes')
        self.assertIsNone(self.catalog.lookup(key(), 'kubernetes'))
        with self.assertRaisesRegex(fc.Refused, 'BUILD_IN_PROGRESS'):
            self.catalog.reserve(key(), 'kubernetes')

    def test_a_dead_builder_or_a_failed_build_can_be_rebuilt(self):
        self.catalog.reserve(key(), 'kubernetes')
        with mock.patch.object(fc, '_alive', return_value=False):
            self.catalog.reserve(key(), 'kubernetes')
        self.catalog.failed(key(), 'kubernetes', 'K8S_X')
        self.assertIsNone(self.catalog.lookup(key(), 'kubernetes'))
        self.built(key())
        self.assertIsNotNone(self.catalog.lookup(key(), 'kubernetes'))

    def test_a_ready_fixture_is_not_built_twice_and_a_retired_one_misses(self):
        record = self.built(key())
        with self.assertRaisesRegex(fc.Refused, 'ALREADY_BUILT'):
            self.catalog.reserve(key(), 'kubernetes')
        self.assertTrue(self.catalog.retire(record['directory']))
        self.assertIsNone(self.catalog.lookup(key(), 'kubernetes'))
        self.built(key())

    def test_a_missing_directory_is_a_miss(self):
        record = self.built(key())
        os.rmdir(record['directory'])
        self.assertIsNone(self.catalog.lookup(key(), 'kubernetes'))

    def test_list_reads_the_catalog(self):
        self.built(key())
        self.assertEqual(json.loads(json.dumps(self.catalog.entries()))[fc.digest(key())]['key'], key())


if __name__ == '__main__':
    unittest.main()


class ComposeRunner(unittest.TestCase):
    """runner.py `prepare.fixture: reuse`: the catalog decides between restore and build-then-register."""
    def setUp(self):
        import runner
        self.runner, self.root = runner, Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.catalog = fc.Catalog(self.root/'catalog.json')
        self.builds = []
        p = mock.patch.object(runner, 'fixture_key', lambda config, seed: key(seed=seed))
        p.start()
        self.addCleanup(p.stop)

    def build(self, config, value, root, catalog):
        directory = catalog.reserve(value, 'compose')
        directory.mkdir(mode=0o700)
        (directory/'key.json').write_text(json.dumps(value))
        self.builds.append((config, root.name))
        return catalog.register(value, 'compose', {'buildCase': str(root)})

    def test_a_hand_named_snapshot_is_refused_and_no_request_is_plain(self):
        with self.assertRaisesRegex(Exception, 'M7_FIXTURE_BY_KEY_REQUIRED'):
            self.runner.fixture_request({'prepare': {'fixture-snapshot': '/x'}})
        self.assertIsNone(self.runner.fixture_request({'prepare': {'tenants': 8}}))
        with self.assertRaisesRegex(Exception, 'M7_FIXTURE_REQUEST'):
            self.runner.fixture_request({'prepare': {'fixture': 'latest'}})

    def test_a_miss_builds_once_then_runs_restore_the_same_copy(self):
        config, seed = self.runner.fixture_request({'prepare': {'tenants': 8, 'fixture': 'reuse', 'fixture-seed': 'n8'}})
        self.assertNotIn('fixture', config['prepare'])
        first, keyed = self.runner.resolve_fixture(config, seed, self.root/'run-1', self.catalog, self.build)
        self.assertEqual((keyed['lookup'], self.builds[0][1]), ('miss', 'run-1-seed'))
        self.assertNotIn('fixture-snapshot', self.builds[0][0]['prepare'])
        second, keyed = self.runner.resolve_fixture(config, seed, self.root/'run-2', self.catalog, self.build)
        self.assertEqual((keyed['lookup'], len(self.builds)), ('hit', 1))
        self.assertEqual(first['prepare']['fixture-snapshot'], second['prepare']['fixture-snapshot'])
        self.assertEqual(keyed['key']['seed'], 'n8')

    def test_a_copy_recorded_under_another_key_is_refused(self):
        config, seed = self.runner.fixture_request({'prepare': {'fixture': 'reuse'}})
        _, keyed = self.runner.resolve_fixture(config, seed, self.root/'run-1', self.catalog, self.build)
        (Path(keyed['snapshot'])/'key.json').write_text(json.dumps(key(tenants=9)))
        with self.assertRaisesRegex(Exception, 'M7_FIXTURE_KEY_CHANGED'):
            self.runner.resolve_fixture(config, seed, self.root/'run-2', self.catalog, self.build)
