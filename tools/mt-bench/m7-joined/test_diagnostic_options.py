"""Actual shared callsites with injected actor ports; no Docker/install/network."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import adapter as a


class DiagnosticOptions(unittest.TestCase):

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

    def test_actual_down_is_one_delete_and_one_absence_check_with_no_source_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'core').mkdir()
            m={'owner':'a'*32,'project':'synthetic-owned','prepared':True,'hostIdentity':'synthetic',
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
            # simple-run-cleanup: no source verifier before the delete; one absence check after it.
            self.assertEqual(recorded,[['docker',kind,'ls','-q','--filter','label=com.docker.compose.project=synthetic-owned'] for kind in ('network','volume')])
            self.assertEqual(a.document(d/'cleanup-absence.json')['status'],'ABSENT')

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

if __name__=='__main__':unittest.main()
