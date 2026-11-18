"""Actual shared callsites with injected actor ports; no Docker/install/network."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
import diagnostic_resources as r
import discovery
import test_generator_setup


class DiagnosticOptions(unittest.TestCase):
    def tearDown(self):
        r.configure()

    def test_missing_or_wrong_scope_options_refuse_before_commands(self):
        for args,code in [
            (SimpleNamespace(diagnostic_resource_profile=r.NAME,profile='capacity',run_purpose='discovery'), 'DISCOVERY_ONLY'),
            (SimpleNamespace(diagnostic_resource_profile=r.NAME,profile='pgstream-sample',run_purpose='discovery'), 'DEPENDENCIES_REQUIRED')]:
            with patch.object(a,'command') as command:
                with self.assertRaisesRegex(RuntimeError,code):a.prepare(args)
                command.assert_not_called()
        for args in [SimpleNamespace(generator_dependencies='/missing'),SimpleNamespace(generator_dependency_preparation='/missing')]:
            with patch.object(a,'command') as command:
                with self.assertRaisesRegex(RuntimeError,'SELECTION_INCOMPLETE'):a.qualified_dependencies(args)
                command.assert_not_called()
        with patch.object(a,'command') as command:
            self.assertIsNone(a.qualified_dependencies(SimpleNamespace()))
            command.assert_not_called()

    def test_command_port_caps_actual_host_node_and_default_is_unchanged(self):
        env={'PATH':'/synthetic'};calls=[]
        def run(argv,**kw):calls.append((argv,kw));return 'synthetic'
        with patch.object(a,'_command',side_effect=run):
            a.command(['node','-e','synthetic'],env=env)
            self.assertEqual(calls[-1][0],['node','-e','synthetic'])
            r.configure(r.NAME)
            a.command(['node','-e','synthetic'],env=env)
            self.assertEqual(calls[-1][0],['node','--max-heap-size=128','-e','synthetic'])
            self.assertEqual(calls[-1][1]['env'],env)
            self.assertFalse(any(r._ACTIVE.host.values()))

    def test_dependency_explicit_cap_composes_with_resource_helper_lease(self):
        with patch.object(a,'_command',return_value='synthetic') as command:
            argv=['node','--max-old-space-size=128','--version']
            a.dependency_run(argv)
            self.assertEqual(command.call_args.args[0],argv)
            r.configure(r.NAME)
            a.dependency_run(argv)
            self.assertEqual(command.call_args.args[0],['node','--max-heap-size=128','--version'])
            with self.assertRaisesRegex(RuntimeError,'NODE_CAP_REQUIRED'):
                a.dependency_run(['node','--max-old-space-size=1024','--version'])

    def test_both_actual_k6_launchers_and_override_refusal(self):
        config={'services':{'api':{}}}
        config=r.overlay(config,r.NAME)
        r.configure(r.NAME,config,observe=lambda:[])
        m=test_generator_setup.SetupConcurrency().manifest(16)
        ordinary=test_generator_setup.SetupConcurrency().direct_command(m)
        selected=discovery.k6_command(a,Path('/tmp/synthetic'),m,'image','run')
        with patch.object(a,'_command',return_value='synthetic') as command:
            for argv in (ordinary,selected):
                a.command(argv)
                actual=command.call_args.args[0]
                self.assertEqual(actual.count('--cpus'),1)
                self.assertEqual(actual.count('--memory'),1)
                self.assertEqual(actual.count('--memory-swap'),1)
                self.assertIn('JWT_SETUP_CONCURRENCY=16',actual)
                self.assertEqual(actual[actual.index('--pull')+1],'never')
            with self.assertRaisesRegex(RuntimeError,'LIMIT_OVERRIDE'):
                a.command(ordinary[:3]+['--cpus','99']+ordinary[3:])

    def test_reuse_setup_copies_without_install_and_copy_failure_has_no_fallback(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as temp:
                d=Path(temp);(d/'core').mkdir();package=b'{}';lock=b'{"lockfileVersion":3}'
                tools={'node':{'path':'/synthetic/node'},'npm':{'path':'/synthetic/npm'}}
                q={'tools':tools,'tree':{'sha256':'synthetic'}}
                m={'pair':{'core':'a'*40,'deploy':'b'*40},'dependencyReuse':q}
                calls=[]
                def command(argv,**kw):
                    calls.append(argv)
                    self.assertEqual(argv[:2],['git','-C'])
                    return lock if str(argv[-1]).endswith(':package-lock.json') else package
                def copy(**kw):
                    if fail:raise RuntimeError('M7_DEPENDENCY_REUSE_COPY_CHANGED')
                    root=kw['destination'];root.mkdir()
                    (root/'package.json').write_bytes(package);(root/'package-lock.json').write_bytes(lock)
                    (root/'node_modules').mkdir()
                    return {'qualification':q,'kind':'owned-qualified-dependency-copy'}
                with patch.object(a,'command',side_effect=command),patch.object(a,'generator_tools',return_value=tools),patch.object(a.dependency_reuse,'copy_owned',side_effect=copy),patch.object(a,'generator_client',return_value={}),patch.object(a,'dependency_context',return_value={}):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError,'COPY_CHANGED'):a.setup_generator(d,m)
                        self.assertNotIn('generator',m)
                    else:
                        a.setup_generator(d,m)
                        self.assertEqual(m['generator']['kind'],'owned-qualified-dependency-copy')
                        self.assertEqual(m['generator']['installFlags'],[])
                        self.assertTrue((d/'core/node_modules').is_symlink())
                        self.assertEqual((d/'core/node_modules').resolve(),d/'dependencies/node_modules')
                self.assertTrue(all('ci' not in argv and 'install' not in argv for argv in calls))

    def test_selected_cleanup_node_cap_does_not_need_resource_admission(self):
        r.configure()
        calls=[]
        def cleanup(d,m):
            a.command(['node','-e','source-verification'])
            raise RuntimeError('ORIGINAL_CLEANUP_FAILURE')
        with patch.object(a,'_down',side_effect=cleanup),patch.object(a,'_command',side_effect=lambda argv,**kw:calls.append(argv)):
            with self.assertRaisesRegex(RuntimeError,'ORIGINAL_CLEANUP_FAILURE'):
                a.down(Path('/synthetic'),{'diagnosticResources':{'invalid':'selected'}})
            self.assertEqual(calls,[['node','--max-heap-size=128','-e','source-verification']])
            self.assertIsNone(r._ACTIVE)
            self.assertFalse(a._CLEANUP_NODE_LIMIT.get())

    def test_actual_down_source_verifier_is_capped_after_resource_bypass(self):
        r.configure()
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'core').mkdir()
            m={'owner':'a'*32,'project':'synthetic-owned','prepared':True,'diagnosticResources':{'invalid':'selected'},'hostIdentity':'synthetic',
               'pair':{'core':'b'*40},'composeSha256':'same','restartHelperSha256':'same',
               'probe':{'adaptedSha256':'same','recoveryHelpers':{'helper':'same'}},'workload':{'adaptedSha256':'same'},
               'sourceCompose':{},'diagnostics':{},'coreRepository':'/synthetic/core'}
            recorded=[]
            def command(argv,**kwargs):
                recorded.append(argv)
                return ''
            with patch.object(a,'assert_owned'),patch.object(a,'fixture_inventory',return_value={}),patch.object(a,'host_identity',return_value='synthetic'),patch.object(a,'git',return_value='b'*40),patch.object(a,'digest',return_value='same'),patch.object(a,'document',return_value={'services':{}}),patch.object(a,'measurement_topology'),patch.object(a.profile_provenance,'verify_environment'),patch.object(a.profile_provenance,'state_environment'),patch.object(a.profile_provenance,'capture_logs',return_value={}),patch.object(a,'compose'),patch.object(a,'resources',return_value=[]),patch.object(a,'_command',side_effect=command):
                a.down(d,m)
            # Teardown now proves exact network/volume absence as well as
            # source identity. Return empty inventories, never error text.
            self.assertEqual(recorded[1:],[['docker',kind,'ls','-q','--filter','label=com.docker.compose.project=synthetic-owned'] for kind in ('network','volume')])
            self.assertEqual(recorded[0][:3],['node','--max-heap-size=128','-e'])
            self.assertIn('assertCleanSource',recorded[0][3])
            self.assertEqual(a.document(d/'cleanup-absence.json')['status'],'ABSENT')
            self.assertIsNone(r._ACTIVE)

    def test_selected_images_are_cached_immutable_and_no_build_recipe_survives(self):
        m={'imageId':'sha256:'+'a'*64}
        config={'services':{'api':{'build':{'context':'source'},'image':'old-tag'},'nginx':{'image':'cached-tag'}}}
        calls=[]
        def inspect(argv,**kw):
            self.assertEqual(argv[:3],['docker','image','inspect']);calls.append(argv)
            return json.dumps([{'Id':m['imageId'] if argv[-1]==m['imageId'] else 'sha256:'+'b'*64}])
        with patch.object(a,'command',side_effect=inspect):
            sealed=a.seal_diagnostic_images(config,m)
        self.assertEqual(sealed['services']['api'],{'image':m['imageId']})
        self.assertEqual(sealed['services']['nginx']['image'],'sha256:'+'b'*64)
        self.assertEqual(len(calls),2)
        with patch.object(a,'command',side_effect=RuntimeError('MISSING_CACHED_IMAGE')):
            with self.assertRaisesRegex(RuntimeError,'MISSING_CACHED_IMAGE'):
                a.seal_diagnostic_images({'services':{'nginx':{'image':'missing'}}},m)

    def test_mutated_owned_copy_refuses_before_other_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'dependencies').mkdir()
            q={'tree':{'sha256':'original'}};proof={'qualification':q}
            (d/'dependencies/dependency-reuse-ready.json').write_text(json.dumps(proof))
            m={'dependencyReuse':q,'generator':{'kind':'owned-qualified-dependency-copy','reuseProvenance':proof}}
            with patch.object(a.dependency_reuse,'tree',return_value={'sha256':'changed'}),patch.object(a,'generator_tools') as tools:
                with self.assertRaisesRegex(RuntimeError,'COPY_CHANGED'):a.verify_generator(d,m)
                tools.assert_not_called()


if __name__=='__main__':unittest.main()
