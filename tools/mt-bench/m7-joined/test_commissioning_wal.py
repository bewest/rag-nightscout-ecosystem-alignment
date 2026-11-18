"""Finite local commissioning retention; actual adapter paths, no runtime actors."""
import contextlib
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
import commissioning_wal as w
import contract as c
import run_configuration as rc
import runner
from test_run_configuration import config, parsed, packet, overlay


def compose():
    roles=('postgres','vault','admin','primer','api','realtime','evaluator','tenant-admin','ui','nginx')
    result={'services':{role:{'command':['synthetic'],'image':'synthetic-cache'} for role in roles}}
    for role in ('api','realtime','evaluator'):result['services'][role]['command']=['node','lib/server/serve/main.js',role]
    result['services']['postgres']['command']=['postgres','-c','wal_level=logical','-c','max_slot_wal_keep_size=256MB']
    return result


def selected(value=1024):
    cfg=config();cfg['prepare']['commissioning-slot-wal-mib']=value
    return cfg


class CommissioningWal(unittest.TestCase):
    def setUp(self):
        pin=patch.object(a,'instrument',return_value={'sha256':'d'*64});pin.start();self.addCleanup(pin.stop)

    def test_omitted_legacy_command_and_projection_are_unchanged(self):
        before=compose();actual=copy.deepcopy(before)
        w.install(actual,{});w.verify(actual,{})
        self.assertEqual(actual,before)
        m,r=packet(config());self.assertNotIn(w.FIELD,m)
        self.assertEqual(rc.from_manifest(m),m['runConfiguration'])
        r.pop('version');self.assertEqual(c.receipt_scope(m,r,'deploy')['functionalAcceptance'],'UNACCEPTED')

    def test_explicit_finite_choices_hash_manifest_and_receipt(self):
        base=rc.from_args(parsed(config()),'d'*64)
        for value in w.VALUES:
            with self.subTest(value=value):
                m,r=packet(selected(value))
                self.assertEqual(m[w.FIELD],value)
                self.assertEqual(rc.from_manifest(m),m['runConfiguration'])
                self.assertNotEqual(rc.sha(base),r['configurationSha256'])
                self.assertEqual(c.receipt_scope(m,r,'deploy')['functionalAcceptance'],'PENDING')
                r.pop('version')
                with self.assertRaisesRegex(RuntimeError,'BOUND_RECEIPT_REQUIRED'):c.receipt_scope(m,r,'deploy')
        self.assertIn('commissioning-slot-wal-mib',runner.SESSION_PREPARE_ONLY)

    def test_bool_values_scope_and_remote_refuse(self):
        for value in (True,False,0,-1,512,2048,'1024',1024.0,None):
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'SLOT_WAL_INVALID'):w.value(value)
        for changes in ({'profile':'remote-pilot'},{'runPurpose':'acceptance'},{'attached':True}):
            m={w.FIELD:1024,'profile':'pgstream-sample','runPurpose':'discovery',**changes}
            with self.subTest(changes=changes),self.assertRaisesRegex(RuntimeError,'LOCAL_DIAGNOSTIC_ONLY'):w.from_manifest(m)
        with self.assertRaisesRegex(RuntimeError,'PREPARE_OPTION'):runner.validate_config(selected(True))
        with self.assertRaisesRegex(RuntimeError,'REMOTE_STARTUP_SELECTION'):rc.remote_projection(selected(),overlay())
        with self.assertRaisesRegex(RuntimeError,'FRESH_PREPARE_ONLY'):a.attach(parsed(selected()))

    def test_exact_token_only_and_baseline_shape_refusal(self):
        m={w.FIELD:1024,'profile':'pgstream-sample','runPurpose':'discovery'}
        original=compose();actual=copy.deepcopy(original);w.install(actual,m)
        expected=copy.deepcopy(original);expected['services']['postgres']['command'][-1]='max_slot_wal_keep_size=1024MB'
        self.assertEqual(actual,expected);w.verify(actual,m)
        for command,code in ((['postgres'],'COMMAND_SHAPE'),(['postgres','-c','max_slot_wal_keep_size=128MB'],'BASELINE_CHANGED'),
                             (['postgres','max_slot_wal_keep_size=256MB'],'COMMAND_SHAPE'),
                             (['postgres','-c','max_slot_wal_keep_size=256MB','-c','max_slot_wal_keep_size=-1'],'COMMAND_SHAPE'),
                             ('postgres -c max_slot_wal_keep_size=256MB','COMMAND_SHAPE')):
            bad=compose();bad['services']['postgres']['command']=command
            with self.subTest(command=command),self.assertRaisesRegex(RuntimeError,code):w.install(bad,m)
        actual['services']['postgres']['command'][-1]='max_slot_wal_keep_size=-1'
        with self.assertRaisesRegex(RuntimeError,'SLOT_WAL_CHANGED'):w.verify(actual,m)
        actual['services']['postgres']['command'][-1]='max_slot_wal_keep_size=1024MB';w.verify(actual,m)

    def test_manifest_receipt_mirror_tamper_and_restoration(self):
        m,r=packet(selected());c.receipt_scope(m,r,'deploy')
        for mutate in (lambda x:x.pop(w.FIELD),lambda x:x.update({w.FIELD:256}),
                       lambda x:x['runConfiguration'].update({w.FIELD:256})):
            bad=copy.deepcopy(m);mutate(bad)
            receipt={**r,'configurationSha256':rc.sha(bad['runConfiguration'])}
            with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH'):c.receipt_scope(bad,receipt,'deploy')
        c.receipt_scope(m,r,'deploy')

    def test_runner_receipt_tamper_before_output_or_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=selected();_,receipt=packet(cfg)
            a.write(root/'receipt.json',receipt);cfg['prepare'].update({'receipt':str(root/'receipt.json'),'commissioning-slot-wal-mib':256})
            a.write(root/'run.json',cfg)
            with patch.object(runner,'arm_window') as guard,patch.object(runner,'stage') as actor:
                with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH'):runner.prepare(root/'run.json',root/'never')
                guard.assert_not_called();actor.assert_not_called();self.assertFalse((root/'never').exists())

    def test_actual_adapter_preflight_mirrors_selected_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=selected();_,receipt=packet(cfg);a.write(root/'receipt.json',receipt)
            cfg['prepare']['receipt']=str(root/'receipt.json');args=parsed(cfg);args.directory=str(root/'never')
            with contextlib.ExitStack() as stack:
                for name in ('commit',):stack.enter_context(patch.object(a,name))
                stack.enter_context(patch.object(rc,'namespace_preflight'))
                stack.enter_context(patch.object(a.os,'getuid',return_value=1000));stack.enter_context(patch.object(a.os,'getgid',return_value=1000))
                effect=stack.enter_context(patch.object(a,'qualified_dependencies',side_effect=RuntimeError('CONTROL_PREFLIGHT_COMPLETE')))
                with self.assertRaisesRegex(RuntimeError,'CONTROL_PREFLIGHT_COMPLETE'):a.prepare(args)
                effect.assert_called_once();self.assertFalse((root/'never').exists())

    def test_actual_verify_refuses_command_tamper_even_with_updated_file_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=compose()
            m={w.FIELD:1024,'profile':'pgstream-sample','runPurpose':'discovery',
               'hostIdentity':'synthetic','pair':{'core':'a'*40}}
            w.install(cfg,m)
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(a,'fixture_inventory',return_value={}))
                stack.enter_context(patch.object(a,'host_identity',return_value='synthetic'))
                stack.enter_context(patch.object(a,'git',return_value='a'*40))
                stack.enter_context(patch.object(a,'platform_startup_config',side_effect=RuntimeError('CONTROL_VERIFY_COMPLETE')))
                for token,code in (('1024MB','CONTROL_VERIFY_COMPLETE'),('-1','SLOT_WAL_CHANGED'),('1024MB','CONTROL_VERIFY_COMPLETE')):
                    cfg['services']['postgres']['command'][-1]='max_slot_wal_keep_size='+token
                    a.write(root/'frozen.compose.json',cfg);m['composeSha256']=a.digest(root/'frozen.compose.json')
                    with self.assertRaisesRegex(RuntimeError,code):a.verify(root,m)

    def test_actual_staged_prepare_installs_before_freeze_red_restored(self):
        def prepare(root,install):
            cfg=selected();m,receipt=packet(cfg);a.write(root/'receipt.json',receipt)
            cfg['prepare']['receipt']=str(root/'receipt.json');args=parsed(cfg);args.resolved_configuration=m['runConfiguration']
            target=root/'fixture';target.mkdir()
            def git(repo,*argv):
                if argv[:3]==('worktree','add','--detach'):(target/'core').mkdir();return ''
                raise AssertionError(('unexpected git',argv))
            def command(argv,**kwargs):
                argv=[str(v) for v in argv];binding=target/'core/deploy/multitenant'
                if argv[0]=='git' and 'archive' in argv:return b''
                if argv[0]=='tar':
                    for name in ('commission-restore.js','publish-primer.js','compose.yaml'):(binding/name).write_text('synthetic\n')
                    return b''
                if argv[0]=='node' and argv[1].endswith('/prepare.js'):
                    (target/'state').mkdir();(binding/'.env').write_text('SYNTHETIC=1\n');return ''
                if argv[:2]==['docker','compose'] and argv[-3:]==['config','--format','json']:return json.dumps(compose())
                if argv[:3]==['docker','image','inspect']:
                    self.assertIn(argv[3],(m['imageId'],'synthetic-cache'))
                    return json.dumps([{'Id':m['imageId']}])
                raise AssertionError(('unexpected actor',argv))
            with contextlib.ExitStack() as stack:
                for name,fn in {'git':git,'command':command,'inventory':lambda *v:{},'host_identity':lambda *v:'synthetic',
                                'resources':lambda *v:[],'port':lambda:12345,'setup_generator':lambda *v:None,'unused_project_namespace':lambda *v:None}.items():
                    stack.enter_context(patch.object(a,name,side_effect=fn))
                stack.enter_context(patch.object(w,'install',side_effect=install));stack.enter_context(patch('builtins.print'))
                a.prepare_staged(args,target,{'sha256':'d'*64})
            owner=a.document(target/'owner.json');frozen=a.document(target/'frozen.compose.json')
            a.frozen(owner,'deploy');self.assertEqual(rc.from_manifest(owner),owner['runConfiguration']);w.verify(frozen,owner)
        actual=w.install
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for label,install in (('green',actual),('red',lambda *v:None),('restored',actual)):
                directory=root/label;directory.mkdir()
                if label=='red':
                    with self.assertRaisesRegex(RuntimeError,'SLOT_WAL_CHANGED'):prepare(directory,install)
                else:prepare(directory,install)


if __name__=='__main__':unittest.main()
