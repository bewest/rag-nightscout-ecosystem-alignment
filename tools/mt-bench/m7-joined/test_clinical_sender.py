"""Synthetic binding/refusal controls; never starts a sender or application."""
import copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import clinical_timeline as t
import diagnostic_resources as r
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
class SenderBinding(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.d=self.root/'fixture';self.d.mkdir(mode=0o700);(self.d/'state').mkdir(mode=0o700);(self.d/'state/pgstream').mkdir(mode=0o700)
        self.binary=self.root/'synthetic-file';self.binary.write_bytes(b'synthetic binding fixture, never executable');self.digest=t.sha(self.binary)
        proof={'kind':'clinical-sender-cli-build-v1','status':'BUILDS_PASS_SOURCE_ONLY','sourceArchiveSha256':'a'*64,'patchSha256':'b'*64,'toolchainSha256':'c'*64,'buildEnvironment':{'CGO_ENABLED':'0'},'binaries':{'instrumented':{'sha256':self.digest}}}
        self.receipt=self.root/'receipt.json';self.receipt.write_text(json.dumps(proof))
        self.meta={'archiveSha256':'a'*64,'patchSha256':'b'*64,'reviewedBuild':{'receiptSha256':t.sha(self.receipt),'instrumentedSha256':self.digest,'instrumentedBytes':self.binary.stat().st_size,'toolchainSha256':'c'*64,'CLIversion':'development','shippingImageBinarySha256':'f'*64}}
        self.stub=patch.object(t,'sender_metadata',return_value=self.meta);self.stub.start();self.addCleanup(self.stub.stop)
        self.config={r.PROFILE_KEY:r.EVALUATOR250_MEMORY512_NAME,'services':{'evaluator':{'command':list(t.COMMAND),'environment':{},'volumes':[]},'api':{'command':['unchanged']},'pgstream':{'command':list(t.SENDER_COMMAND),'environment':{},'volumes':[{'type':'bind','source':str(self.d/'state/pgstream'),'target':'/run/ns-stream','read_only':True}],'cpus':'0.125','mem_limit':268435456,'memswap_limit':268435456}}}
        self.m={'profile':'pgstream-sample','runPurpose':'discovery','pgstreamTopology':'external-service-v1','imageId':'sha256:'+'e'*64}
    def install(self):t.install(self.config,self.d,self.m,t.RAW_NAME,str(self.binary),str(self.receipt));t.verify(self.config,self.d,self.m)
    def publish(self):
        for name in ('bootstrap','evaluator'):(self.d/'state'/name).mkdir()
        (self.d/'state/bootstrap/layout.json').write_text(json.dumps({'namespaces':{'clock':'nsdemo_clock'}}));(self.d/'state/evaluator/config.json').write_text(json.dumps({'postgres':{'namespaces':{'clock':'nsdemo_clock'}}}))
        t.publish(self.d,self.m,[{'id':A},{'id':B}]);t.verify(self.config,self.d,self.m)
    def test_defaultoff_and_v1_refuse_untracked_or_partial_sender_selection(self):
        config=copy.deepcopy(self.config);m=copy.deepcopy(self.m);t.install(self.config,self.d,self.m,'off');self.assertEqual(self.config,config);self.assertEqual(self.m,m)
        for binary,receipt,selection in [(str(self.binary),None,t.RAW_NAME),('', '', t.RAW_NAME),(str(self.binary),str(self.receipt),t.NAME),(str(self.binary),str(self.receipt),'off')]:
            with self.assertRaisesRegex(RuntimeError,'SELECTION'):t.install(self.config,self.d,self.m,selection,binary,receipt)
        self.config['services']['pgstream']['environment'][t.SENDER_ENV]='1'
        with self.assertRaisesRegex(RuntimeError,'RECORD_REQUIRED'):t.verify(self.config,self.d,self.m)
    def test_actual_proc_reader_uses_owned_process_bytes_and_birth(self):
        evidence=t.process_evidence(os.getpid());self.assertEqual(evidence['pid'],os.getpid());self.assertEqual(evidence['uid'],os.geteuid());self.assertEqual(evidence['executableSha256'],t.sha(Path('/proc')/str(os.getpid())/'exe'))
        original=Path.read_text;count=0;target=Path('/proc')/str(os.getpid())/'stat'
        def changed(path,*args,**kwargs):
            nonlocal count
            value=original(path,*args,**kwargs)
            if path==target:
                count+=1
                if count==2:
                    head,tail=value.rsplit(')',1);fields=tail.split();fields[19]=str(int(fields[19])+1);return head+') '+' '.join(fields)
            return value
        with patch.object(Path,'read_text',changed):
            with self.assertRaisesRegex(RuntimeError,'PROCESS_REPLACED'):t.process_evidence(os.getpid())
    def test_exact_owned_copy_scope_and_defaultoff(self):
        old=copy.deepcopy(self.config);self.install();self.assertEqual(self.config['services']['api'],old['services']['api']);self.assertEqual(self.config['services']['pgstream']['command'],old['services']['pgstream']['command'])
        for field in ('cpus','mem_limit','memswap_limit'):self.assertEqual(self.config['services']['pgstream'][field],old['services']['pgstream'][field])
        staged=self.d/'state/clinical-sender-binary/pgstream';self.assertEqual(t.sha(staged),self.digest);self.assertNotEqual(staged.stat().st_ino,self.binary.stat().st_ino);self.assertEqual(staged.stat().st_mode&0o777,0o555)
        self.assertNotEqual((self.d/'state/clinical-sender-output').resolve(),(self.d/'state/ipc').resolve())
    def test_wrong_hash_and_topology_and_role_refuse_before_staging(self):
        original=self.binary.read_bytes();self.binary.write_bytes(b'wrong')
        with self.assertRaisesRegex(RuntimeError,'BINARY'):self.install()
        self.assertFalse((self.d/'state/clinical-sender-binary').exists())
        self.binary.write_bytes(original)
        # Start fresh after the deliberate failed Node-preload preparation.
        self.setUp()
        for field,value in [('pgstreamTopology','colocated-v1'),('profile','other')]:
            original=self.m[field];self.m[field]=value
            with self.assertRaisesRegex(RuntimeError,'SCOPE'):t.install_sender(self.config,self.d,{**self.m,'clinicalTimeline':{'selection':t.RAW_NAME}},self.binary,self.receipt)
            self.m[field]=original
        original=self.config['services']['pgstream']['command'];self.config['services']['pgstream']['command']=['sh','-c','unapproved']
        with self.assertRaisesRegex(RuntimeError,'ROLE'):t.install_sender(self.config,self.d,{**self.m,'clinicalTimeline':{'selection':t.RAW_NAME}},self.binary,self.receipt)
        self.config['services']['pgstream']['command']=original;self.install()
    def test_preexisting_unsafe_nonowned_and_extra_mount_refuse(self):
        output=self.d/'state/clinical-sender-output';output.mkdir();(output/'prior').write_text('preserve')
        with self.assertRaisesRegex(RuntimeError,'PREEXISTING_OUTPUT'):t.install_sender(self.config,self.d,{**self.m,'clinicalTimeline':{'selection':t.RAW_NAME}},self.binary,self.receipt)
        self.assertEqual((output/'prior').read_text(),'preserve');(output/'prior').unlink();output.rmdir()
        self.config['services']['pgstream']['volumes'].append({'source':'/unapproved','target':'/extra','read_only':True})
        with self.assertRaisesRegex(RuntimeError,'EXTRA_MOUNT'):t.install_sender(self.config,self.d,{**self.m,'clinicalTimeline':{'selection':t.RAW_NAME}},self.binary,self.receipt)
        self.config['services']['pgstream']['volumes'].pop();self.install();output.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError,'PERMISSIONS'):t.verify(self.config,self.d,self.m)
        output.chmod(0o700)
        with patch.object(t.os,'geteuid',return_value=os.geteuid()+1):
            with self.assertRaisesRegex(RuntimeError,'OWNER'):t.verify(self.config,self.d,self.m)
        t.verify(self.config,self.d,self.m)
    def test_unknown_schema_and_preexisting_target_and_before_effect_refuse(self):
        self.install()
        with self.assertRaisesRegex(RuntimeError,'TARGETS'):t.before_sender_effect(self.d,['up','pgstream'],self.config,self.m)
        for name in ('bootstrap','evaluator'):(self.d/'state'/name).mkdir()
        layout=self.d/'state/bootstrap/layout.json';receiver=self.d/'state/evaluator/config.json';layout.write_text(json.dumps({'namespaces':{'clock':'unknown'}}));receiver.write_text(json.dumps({'postgres':{'namespaces':{'clock':'unknown'}}}))
        with self.assertRaisesRegex(RuntimeError,'SCHEMA'):t.publish_sender(self.d,self.m,[A,B])
        self.assertFalse((self.d/'state/clinical-sender-targets/targets.json').exists())
        layout.write_text(json.dumps({'namespaces':{'clock':'nsdemo_clock'}}));receiver.write_text(json.dumps({'postgres':{'namespaces':{'clock':'nsdemo_clock'}}}));target=self.d/'state/clinical-sender-targets/targets.json';target.write_text('prior')
        with self.assertRaisesRegex(RuntimeError,'PREEXISTING_FILE'):t.publish_sender(self.d,self.m,[A,B])
        self.assertEqual(target.read_text(),'prior');target.unlink();t.publish(self.d,self.m,[{'id':A},{'id':B}]);t.before_sender_effect(self.d,['up','pgstream'],self.config,self.m)
        (self.d/'state/clinical-sender-output/clinical-sender-timeline.jsonl').write_text('prior')
        with self.assertRaisesRegex(RuntimeError,'PREEXISTING_OUTPUT'):t.before_sender_effect(self.d,['up','pgstream'],self.config,self.m)
    def test_wrong_role_mount_and_symlink_and_postcopy_hash_refuse(self):
        self.install();mount=copy.deepcopy(self.config['services']['pgstream']['volumes'][1]);self.config['services']['api']['volumes']=[mount]
        with self.assertRaisesRegex(RuntimeError,'WRONG_ROLE'):t.verify(self.config,self.d,self.m)
        del self.config['services']['api']['volumes'];staged=self.d/'state/clinical-sender-binary/pgstream';staged.chmod(0o755);staged.write_bytes(b'changed');staged.chmod(0o555)
        with self.assertRaisesRegex(RuntimeError,'BINARY'):t.verify(self.config,self.d,self.m)
        staged.unlink();staged.symlink_to(self.binary)
        with self.assertRaisesRegex(RuntimeError,'PATH'):t.verify(self.config,self.d,self.m)
    def test_runtime_requires_actual_primary_exe_birth_and_mounts(self):
        self.install();self.publish();record=self.m['clinicalSender'];row={'Id':'container','Image':self.m['imageId'],'Config':{'Cmd':list(t.SENDER_COMMAND),'Env':[t.SENDER_ENV+'=1'],'Labels':{'com.docker.compose.service':'pgstream'}},'State':{'Running':True,'Pid':100},'Mounts':[{'Type':'bind','Source':m['source'],'Destination':m['target'],'RW':not m.get('read_only',False)} for m in self.config['services']['pgstream']['volumes']]};snapshot={'id':'container','hostProcesses':{'101':{'component':'pgstream','startTicks':123}}};evidence={'pid':101,'birth':'123','uid':os.geteuid(),'executable':t.SENDER_BINARY,'executableSha256':self.digest}
        with patch.object(t,'process_evidence',return_value=evidence):self.assertEqual(t.sender_runtime(self.d,self.m,[row],snapshot)['actualPrimary'],evidence)
        for field,value in [('birth','124'),('executableSha256','0'*64),('executable','/other'),('uid',os.geteuid()+1)]:
            with patch.object(t,'process_evidence',return_value={**evidence,field:value}):
                with self.assertRaisesRegex(RuntimeError,'RUNTIME_EXECUTABLE'):t.sender_runtime(self.d,self.m,[row],snapshot)
        snapshot['hostProcesses']={'100':{'component':'pgstream','startTicks':123}}
        with self.assertRaisesRegex(RuntimeError,'PID1_SUBSTITUTE'):t.sender_runtime(self.d,self.m,[row],snapshot)
    def test_actual_compose_gateway_refuses_before_effect_omission_red_restored(self):
        import adapter as a,inspect
        self.install();self.publish();(self.d/'owner.json').write_text(json.dumps(self.m));(self.d/'frozen.compose.json').write_text(json.dumps(self.config))
        staged=self.d/'state/clinical-sender-binary/pgstream';staged.chmod(0o755);staged.write_bytes(b'changed');staged.chmod(0o555)
        source=inspect.getsource(a.compose);needle="        clinical_timeline.before_sender_effect(Path(d),args,document(Path(d)/'frozen.compose.json'),document(Path(d)/'owner.json'))";self.assertEqual(source.count(needle),1)
        namespace=dict(a.__dict__);exec(compile(source.replace(needle,'        pass # deliberate omitted sender pre-effect gate'),a.__file__,'exec'),namespace);broken=namespace['compose']
        with patch.object(a.diagnostic_resources,'_ACTIVE',None),patch.object(a.orchestration_binding,'fixture_argv',return_value=['synthetic-compose']),patch.object(a.orchestration_binding,'fixture_mutation_preflight') as mutation,patch.object(a,'command',return_value='synthetic-effect') as effect:
            namespace['command']=effect
            def refusal(caller):
                with self.assertRaisesRegex(RuntimeError,'BINARY'):caller(self.d,'up','pgstream')
            refusal(a.compose);mutation.assert_not_called();effect.assert_not_called()
            with self.assertRaises(AssertionError):refusal(broken)
            mutation.reset_mock();effect.reset_mock();refusal(a.compose);mutation.assert_not_called();effect.assert_not_called()
            staged.chmod(0o755);staged.write_bytes(self.binary.read_bytes());staged.chmod(0o555)
            self.assertEqual(a.compose(self.d,'up','pgstream'),'synthetic-effect');mutation.assert_called_once();effect.assert_called_once()
    def test_corrupt_missing_sender_files_refuse_start_but_not_owned_teardown(self):
        import adapter as a
        self.install();self.publish();(self.d/'owner.json').write_text(json.dumps(self.m));(self.d/'frozen.compose.json').write_text(json.dumps(self.config))
        without_record={key:value for key,value in self.m.items() if key!='clinicalSender'}
        with self.assertRaisesRegex(RuntimeError,'RECORD_REQUIRED'):t.before_sender_effect(self.d,['up','pgstream'],self.config,without_record)
        staged=self.d/'state/clinical-sender-binary/pgstream';staged.unlink()
        with self.assertRaises((RuntimeError,FileNotFoundError)):t.before_sender_effect(self.d,['up','pgstream'],self.config,self.m)
        self.assertEqual(t.sender_cleanup_observation(self.config,self.d,self.m)['status'],'UNMEASURED');t.verify(self.config,self.d,self.m,teardown=True)
        with patch.object(a.diagnostic_resources,'_ACTIVE',None),patch.object(a.orchestration_binding,'fixture_argv',return_value=['synthetic-owned-compose']),patch.object(a.orchestration_binding,'fixture_mutation_preflight') as ownership,patch.object(a,'command',return_value='owned-teardown') as effect:
            self.assertEqual(a.compose(self.d,'down','--volumes'),'owned-teardown');ownership.assert_called_once();effect.assert_called_once()
        # A missing receipt also refuses new effects, without preventing stop.
        staged.write_bytes(self.binary.read_bytes());staged.chmod(0o555);(staged.parent/'build-receipt.json').unlink()
        with self.assertRaises((RuntimeError,FileNotFoundError)):t.before_sender_effect(self.d,['up','pgstream'],self.config,self.m)
        t.before_sender_effect(self.d,['stop','pgstream'],self.config,self.m)
    def test_actual_down_keeps_ownership_and_retains_partial_when_binary_missing(self):
        import adapter as a
        self.install();self.publish();self.m.update(prepared=True,owner='synthetic-owner',project='synthetic-owned')
        (self.d/'state/clinical-sender-binary/pgstream').unlink();output=self.d/'state/clinical-sender-output'
        file=output/'clinical-sender-timeline.jsonl';file.write_text('{"phase":"message-ready"}\n');file.chmod(0o600)
        with patch.object(a,'verify',side_effect=lambda directory,metadata,teardown=False:t.verify(self.config,directory,metadata,teardown=teardown)) as check,patch.object(a,'assert_owned') as ownership,patch.object(a,'compose') as teardown,patch.object(a,'resources',return_value=[]),patch.object(a.profile_provenance,'capture_logs',return_value={'complete':False}):
            (self.d/'frozen.compose.json').write_text(json.dumps(self.config));a._down(self.d,self.m)
            check.assert_called_once_with(self.d,self.m,teardown=True);ownership.assert_called_once_with(self.m);teardown.assert_called_once()
        self.assertFalse((self.d/'state').exists());self.assertEqual((self.d/'clinical-timeline/clinical-sender-timeline.jsonl').read_text(),'{"phase":"message-ready"}\n')
        captured=[json.loads(file.read_text()) for file in self.d.glob('clinical-sender-cleanup-observation-*.json')];self.assertEqual(len(captured),1);self.assertEqual(captured[0]['status'],'UNMEASURED')
    def test_sender_retention_is_bounded_partial_and_never_clinical_green(self):
        self.install();self.publish();out=self.d/'state/clinical-sender-output';(out/'clinical-sender-timeline.jsonl').write_text('{"phase":"message-ready"}\n');(out/'clinical-sender-status.json').write_text('{"qualification":"CAPTURED_REQUIRES_STRUCTURAL_CHECK"}');(out/'clinical-sender-timeline.jsonl').chmod(0o600);(out/'clinical-sender-status.json').chmod(0o600)
        result=t.retain(self.d,self.m);self.assertEqual(result['status'],'UNMEASURED');self.assertIn('clinical-sender-timeline.jsonl',result['files']);self.assertIn('UNMEASURED',result['senderQualification'])
if __name__=='__main__':unittest.main()
