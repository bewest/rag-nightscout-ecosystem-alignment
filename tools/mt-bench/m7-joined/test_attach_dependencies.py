"""File-only attachment dependency binding; no Docker, SQL, install or traffic."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import adapter as a

class AttachmentDependencies(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.fixture=Path(self.temp.name)/'fixture';self.fixture.mkdir()
        self.source=self.fixture/'core';self.root=self.fixture/'dependencies';self.target=Path(self.temp.name)/'attachment'
        self.files={'package.json':b'{"name":"synthetic"}', 'package-lock.json':b'{"lockfileVersion":3}'}
        for directory in (self.source,self.root,self.target):directory.mkdir()
        for directory in (self.source,self.root):
            for name,value in self.files.items():(directory/name).write_bytes(value)
        (self.target/'dependencies').symlink_to(self.root,target_is_directory=True)
        self.m={'pair':{'core':'a'*40,'deploy':'b'*40},'imageId':'sha256:'+'c'*64,'project':'synthetic','runtimeOwnerLabels':['d'*32]}
        self.tools={'node':{'path':'/synthetic/node'},'npm':{'path':'/synthetic/npm'}}
        self.client={'entry':str(self.root/'node_modules/socket.io-client/index.js'),'version':'4.8.3','entrySha256':'e'*64}
        self.contexts={'generator':{'root':str(self.root),'cwd':'original-instrument','packageSha256':'synthetic'},
                       'source':{'root':str(self.source),'cwd':'original-instrument','packageSha256':'synthetic'}}
        generator={'kind':'owned-lockfile-install','pair':self.m['pair'],'servingImageId':self.m['imageId'],
                   'packageSha256':hashlib.sha256(self.files['package.json']).hexdigest(),
                   'lockSha256':hashlib.sha256(self.files['package-lock.json']).hexdigest(),
                   'tools':self.tools,'client':self.client,'contexts':self.contexts}
        self.owner={'directory':str(self.fixture),'owner':'d'*32,'prepared':True,'project':self.m['project'],'pair':self.m['pair'],
                    'imageId':self.m['imageId'],'instrument':{'sha256':'f'*64},'generator':generator}
        self.owner_file=self.fixture/'owner.json';self.provenance=self.fixture/'generator-provenance.json';self.save()
        self.command=patch.object(a,'command',side_effect=lambda argv,**kw:self.files[argv[-1].split(':')[-1]]).start();self.addCleanup(patch.stopall)
        patch.object(a,'generator_tools',return_value=self.tools).start()
        self.client_mock=patch.object(a,'generator_client',return_value=self.client).start()
        def context(root,*args):return {**copy.deepcopy(self.contexts['source' if root==self.source else 'generator']),'cwd':'current-instrument'}
        self.context_mock=patch.object(a,'dependency_context',side_effect=context).start()
    def save(self):
        self.owner_file.write_text(json.dumps(self.owner));self.provenance.write_text(json.dumps(self.owner['generator']))
    def run_binding(self,root=None,owner=True):
        return a.attachment_generator(self.target,self.source,root or self.root,self.m,self.owner_file if owner else None)
    def test_actual_attach_manifest_retains_explicit_diagnostics_arguments(self):
        state=self.fixture/'state';state.mkdir();target=self.fixture.parent/'fresh-attachment'
        args=SimpleNamespace(fixture_project=None,profile='pgstream-sample',run_purpose='discovery',
             core_repo='synthetic',core_commit=self.m['pair']['core'],deploy_repo='synthetic',deploy_commit=self.m['pair']['deploy'],
             source_root=self.source,state=state,directory=target,project='synthetic',image='sha256:'+'c'*64,
             image_id='sha256:'+'c'*64,tenants=1,replicas=1,freeze=self.fixture/'receipt.json',quiet_load=0,
             diagnostics='on',diagnostics_interval_ms=2500,completion_contract='evaluator-work-v2',static_workers=1,runtime_owner=str(self.owner_file))
        self.owner.update(inputTransport='writer-driven',staticTopology={'kind':'static-hash-v1','workers':1},replicas=1);self.save()
        def admission(manifest,operation):
            self.assertEqual(manifest['diagnostics'],a.profile_provenance.selection('on',2500))
            raise RuntimeError('M7_TEST_STOP_BEFORE_RESOURCE_ACCESS')
        with patch.object(a,'instrument',return_value={'sha256':'f'*64}),patch.object(a,'commit',side_effect=lambda repo,value:value),             patch.object(a,'git',return_value=args.core_commit),patch.object(a,'frozen',side_effect=admission),patch.object(a,'image') as image:
            with self.assertRaisesRegex(RuntimeError,'TEST_STOP_BEFORE_RESOURCE_ACCESS'):a.attach(args)
            image.assert_not_called()
        self.assertFalse(target.exists())
    def test_canonical_owner_binds_exact_roots_lock_and_prior_context(self):
        value=self.run_binding()
        self.assertEqual(value['runtimeOwner']['owner'],self.owner['owner'])
        self.assertEqual(value['contexts']['generator']['cwd'],'current-instrument')
        self.client_mock.assert_called_once_with(self.target,self.tools)
        self.context_mock.assert_any_call(self.source,self.root/'node_modules',['pg','js-yaml'])
    def test_historical_direct_tree_keeps_source_root_without_owner_requirement(self):
        value=self.run_binding(root=self.source,owner=False)
        self.assertNotIn('runtimeOwner',value)
        self.context_mock.assert_any_call(self.source,self.source/'node_modules',['pg','js-yaml'])
    def test_wrong_dependency_lock_and_dirty_source_refuse_then_restore(self):
        for directory,code in [(self.root,'DEPENDENCY_LOCK_CHANGED'),(self.source,'SOURCE_LOCK_CHANGED')]:
            lock=directory/'package-lock.json';original=lock.read_bytes();lock.write_bytes(original+b' ')
            with self.assertRaisesRegex(RuntimeError,code):self.run_binding()
            lock.write_bytes(original);self.run_binding()
    def test_peer_root_and_wrong_runtime_owner_refuse_then_restore(self):
        peer=Path(self.temp.name)/'peer';peer.mkdir()
        for name,value in self.files.items():(peer/name).write_bytes(value)
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_DEPENDENCY_ROOT'):self.run_binding(peer)
        self.m['runtimeOwnerLabels']=['0'*32]
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_OWNER_MISMATCH'):self.run_binding()
        self.m['runtimeOwnerLabels']=['d'*32];self.run_binding()
    def test_qualified_copy_retains_ready_receipt_and_context_checks(self):
        qualification={'version':2,'source':str(self.root)}
        self.owner['dependencyReuse']=qualification
        self.owner['generator'].update(kind='owned-qualified-dependency-copy',reuseProvenance={'qualification':qualification})
        self.save();ready=self.root/'dependency-reuse-ready.json';ready.write_text(json.dumps(self.owner['generator']['reuseProvenance']))
        self.run_binding()
        ready.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_COPY_CHANGED'):self.run_binding()
        ready.write_text(json.dumps(self.owner['generator']['reuseProvenance']));self.run_binding()
        self.client_mock.return_value={**self.client,'entrySha256':'0'*64}
        with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_CONTEXT_CHANGED'):self.run_binding()
        self.client_mock.return_value=self.client;self.run_binding()
        self.tools['node']['path']='/synthetic/changed-node'
        with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_CONTEXT_CHANGED'):self.run_binding()

    def test_owner_provenance_and_actual_client_context_drift_refuse(self):
        original=self.provenance.read_bytes();self.provenance.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_GENERATOR_CHANGED'):self.run_binding()
        self.provenance.write_bytes(original)
        self.client_mock.return_value={**self.client,'entrySha256':'0'*64}
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_DEPENDENCY_CONTEXT_CHANGED'):self.run_binding()
        self.client_mock.return_value=self.client;self.run_binding()

if __name__=='__main__':unittest.main()
