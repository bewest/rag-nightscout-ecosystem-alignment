import copy,json,tempfile,unittest
from pathlib import Path
import clinical_timeline as t
import diagnostic_resources as r
class Timeline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.d=Path(self.temp.name);(self.d/'state').mkdir()
        self.config={r.PROFILE_KEY:r.EVALUATOR250_MEMORY512_NAME,'services':{'evaluator':{'command':list(t.COMMAND),'environment':{},'volumes':[]},'api':{'command':['unchanged']}}};self.m={'runPurpose':'discovery'}
    def test_off_unchanged_and_only_owned_preload_changes_selected_evaluator(self):
        old=copy.deepcopy(self.config);t.install(self.config,self.d,self.m,'off');self.assertEqual(self.config,old);self.assertNotIn('clinicalTimeline',self.m)
        t.install(self.config,self.d,self.m,t.NAME);t.verify(self.config,self.d,self.m)
        self.assertEqual(self.config['services']['api'],old['services']['api']);self.assertEqual(self.config['services']['evaluator']['command'][-1],'evaluator')
        e=copy.deepcopy(self.config['services']['evaluator']);e['command']=list(t.COMMAND);e['environment'].pop('NS_M7_CLINICAL_TIMELINE');e['volumes'].pop();self.assertEqual(e,old['services']['evaluator'])
    def test_wrong_profile_argv_mount_and_bytes_red_restored(self):
        for change,code in [(lambda c:c.update({r.PROFILE_KEY:r.EVALUATOR250_NAME}),'SCOPE'),(lambda c:c['services']['evaluator'].update(command=['wrong']),'COMMAND')]:
            broken=copy.deepcopy(self.config);change(broken)
            with self.assertRaisesRegex(RuntimeError,code):t.install(broken,self.d,copy.deepcopy(self.m),t.NAME)
        t.install(self.config,self.d,self.m,t.NAME)
        with self.assertRaisesRegex(RuntimeError,'RECORD_REQUIRED'):t.verify(self.config,self.d,{})
        broken=copy.deepcopy(self.config);broken['services']['evaluator']['volumes'][0]['read_only']=False
        with self.assertRaisesRegex(RuntimeError,'MOUNT'):t.verify(broken,self.d,self.m)
        file=self.d/'state/clinical-timeline/preload.cjs';original=file.read_bytes();file.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'BYTES'):t.verify(self.config,self.d,self.m)
        file.write_bytes(original);t.verify(self.config,self.d,self.m)
    def test_targets_publish_after_prime_without_tokens_and_changed_target_refuses(self):
        t.install(self.config,self.d,self.m,t.NAME);A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
        t.publish(self.d,self.m,[{'id':A,'token':'synthetic-not-for-evaluator'},{'id':B,'token':'synthetic-not-for-evaluator'}]);file=self.d/'state/clinical-timeline/targets.json'
        original=file.read_bytes();self.assertEqual(json.loads(original),{'ids':[A,B]});self.assertNotIn(b'token',original);t.verify(self.config,self.d,self.m)
        file.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'TARGETS'):t.verify(self.config,self.d,self.m)
        file.write_bytes(original);t.verify(self.config,self.d,self.m)
    def test_partial_trace_survives_missing_exit_status_and_does_not_claim_complete(self):
        self.m['clinicalTimeline']={};self.m['clinicalTimeline']['selection']=t.NAME
        ipc=self.d/'state/ipc';ipc.mkdir();(ipc/'clinical-intake-timeline.jsonl').write_text('{"phase":"observe-call"}\n')
        result=t.retain(self.d,self.m);self.assertEqual(result['status'],'UNMEASURED');self.assertEqual((self.d/'clinical-timeline/clinical-intake-timeline.jsonl').read_text(),'{"phase":"observe-call"}\n');self.assertEqual(len(result['refusals']),1)

    def test_raw_selection_is_explicit_and_omission_red_restored(self):
        t.install(self.config,self.d,self.m,t.RAW_NAME);t.verify(self.config,self.d,self.m)
        e=self.config['services']['evaluator']['environment'];e.pop('NS_M7_CLINICAL_RAW_TIMELINE')
        with self.assertRaisesRegex(RuntimeError,'RAW_SELECTION'):t.verify(self.config,self.d,self.m)
        e['NS_M7_CLINICAL_RAW_TIMELINE']='1';t.verify(self.config,self.d,self.m)
        self.m['clinicalTimeline']['raw']['maxRows']+=1
        with self.assertRaisesRegex(RuntimeError,'RAW_RECORD'):t.verify(self.config,self.d,self.m)
        self.m['clinicalTimeline']['raw']['maxRows']-=1;t.verify(self.config,self.d,self.m)
    def test_raw_retention_requires_independent_status_and_terminal_coverage(self):
        t.install(self.config,self.d,self.m,t.RAW_NAME);ipc=self.d/'state/ipc';ipc.mkdir()
        (ipc/'clinical-intake-timeline.jsonl').write_text('')
        (ipc/'clinical-intake-timeline-status.json').write_text(json.dumps({'qualification':'COMPLETE','rows':0,'bytes':0,'written':0,'pending':0,'dropped':0,'failed':None,'closed':False}))
        row={'instance':'11111111-1111-4111-8111-111111111111','sequence':1,'phase':'raw-entry','at':1,'monoNs':'1','pid':1,'request':1,'headerLsn':'0/100','idempotency':'0/100','connection':None,'peerPort':None,'localPort':None}
        raw=ipc/'clinical-intake-raw.jsonl';raw.write_text(json.dumps(row)+'\n');status={'instance':row['instance'],'qualification':'COMPLETE','rows':1,'written':1,'bytes':raw.stat().st_size,'pending':0,'dropped':0,'failed':None,'closed':False}
        self.assertFalse(t.raw_complete(raw,status),'MISSING_TERMINAL_MUST_REFUSE')
        second={key:value for key,value in row.items() if key not in ('connection','peerPort','localPort')};second.update(sequence=2,phase='raw-request-aborted')
        raw.write_text(json.dumps(row)+'\n'+json.dumps(second)+'\n');status.update(rows=2,written=2,bytes=raw.stat().st_size)
        self.assertTrue(t.raw_complete(raw,status));(ipc/'clinical-intake-raw-status.json').write_text(json.dumps(status))
        self.assertEqual(t.retain(self.d,self.m)['status'],'COMPLETE')
        second['arbitrary']='DO_NOT_EMIT';raw.write_text(json.dumps(row)+'\n'+json.dumps(second)+'\n');status['bytes']=raw.stat().st_size
        self.assertFalse(t.raw_complete(raw,status),'ARBITRARY_FIELD_MUST_REFUSE')

class CaptureIntegrity(unittest.TestCase):
    instance='11111111-1111-4111-8111-111111111111'
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.counter=0
    def rows(self,incomplete=False):
        base={'instance':self.instance,'at':1,'monoNs':'1','pid':1,'request':1,'headerLsn':'0/100','idempotency':'0/100'}
        entry={**base,'sequence':1,'phase':'raw-entry','connection':1,'peerPort':10000,'localPort':19913}
        if incomplete:return [entry,{**base,'sequence':2,'phase':'raw-request-close','complete':False,'aborted':False},{**base,'sequence':3,'phase':'raw-response-close','status':503,'finished':False}]
        return [entry,{**base,'sequence':2,'phase':'raw-request-aborted'}]
    def artifact(self,rows):
        self.counter+=1;file=self.root/str(self.counter);file.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        status={'instance':self.instance,'qualification':'COMPLETE','rows':len(rows),'bytes':file.stat().st_size,'written':len(rows),'pending':0,'dropped':0,'failed':None,'closed':False}
        return file,status
    def selected(self,status):
        self.counter+=1;folder=self.root/str(self.counter);ipc=folder/'state/ipc';ipc.mkdir(parents=True)
        (ipc/'clinical-intake-timeline.jsonl').write_text('');(ipc/'clinical-intake-timeline-status.json').write_text(json.dumps(status))
        return t.retain(folder,{'clinicalTimeline':{'selection':t.NAME}})['status']
    def test_status_field_omissions_and_falseys_refuse_raw_and_selected(self):
        file,raw=self.artifact(self.rows());selected={key:value for key,value in raw.items() if key!='instance'};selected.update(rows=0,written=0,bytes=0)
        self.assertTrue(t.raw_complete(file,raw));self.assertEqual(self.selected(selected),'COMPLETE')
        for key in raw:
            with self.subTest(raw_missing=key):
                broken=copy.deepcopy(raw);del broken[key];self.assertFalse(t.raw_complete(file,broken),'STATUS_FIELD_REQUIRED')
        for key in selected:
            with self.subTest(selected_missing=key):
                broken=copy.deepcopy(selected);del broken[key];self.assertEqual(self.selected(broken),'UNMEASURED','SELECTED_STATUS_FIELD_REQUIRED')
        for key in ('pending','dropped','failed'):
            for value in (False,'',[],{},0.0):
                with self.subTest(key=key,value=value):
                    self.assertFalse(t.raw_complete(file,{**raw,key:value}),'RAW_FALSEY_NOT_ZERO')
                    self.assertEqual(self.selected({**selected,key:value}),'UNMEASURED','SELECTED_FALSEY_NOT_ZERO')
        for key in ('rows','bytes','written','pending','dropped'):
            for value in (False,True,-1,9007199254740992,'0',None):
                with self.subTest(counter=key,value=value):
                    self.assertFalse(t.raw_complete(file,{**raw,key:value}))
                    self.assertEqual(self.selected({**selected,key:value}),'UNMEASURED')
        for key,value in [('closed',0),('closed',None),('qualification',True),('arbitrary','extra')]:
            self.assertFalse(t.raw_complete(file,{**raw,key:value}));self.assertEqual(self.selected({**selected,key:value}),'UNMEASURED')
        self.assertTrue(t.raw_complete(file,raw));self.assertEqual(self.selected(selected),'COMPLETE')
    def test_lifecycle_and_connection_types_ranges_and_schema_refuse(self):
        base=self.rows(incomplete=True);file,status=self.artifact(base);self.assertTrue(t.raw_complete(file,status),'INCOMPLETE_RESPONSE_IS_CAPTURE_METADATA')
        mutations={0:{'connection':[False,0,-1,32769,'1',[]],'peerPort':[False,0,-1,65536,'10000',[]],'localPort':[False,0,-1,65536,'19913',[]]},1:{'complete':[0,'false',None,[]],'aborted':[0,'false',None,[]]},2:{'status':[False,99,1000,'503',None,[]],'finished':[0,'false',None,[]]}}
        for index,fields in mutations.items():
            for field,values in fields.items():
                for value in values:
                    with self.subTest(index=index,field=field,value=value):
                        changed=copy.deepcopy(base);changed[index][field]=value;file,status=self.artifact(changed);self.assertFalse(t.raw_complete(file,status),'PHASE_VALUE_CONTRACT')
                changed=copy.deepcopy(base);del changed[index][field];file,status=self.artifact(changed);self.assertFalse(t.raw_complete(file,status),'PHASE_FIELD_REQUIRED')
        for index in range(len(base)):
            changed=copy.deepcopy(base);changed[index]['arbitrary']='extra';file,status=self.artifact(changed);self.assertFalse(t.raw_complete(file,status))
        file,status=self.artifact(base);self.assertTrue(t.raw_complete(file,status))
    def test_terminal_semantics_and_identity_preserve_incomplete_observations(self):
        rows=self.rows(incomplete=True);file,status=self.artifact(rows);self.assertTrue(t.raw_complete(file,status))
        finish=copy.deepcopy(rows);finish[-1].update(phase='raw-response-finish',finished=False);file,status=self.artifact(finish);self.assertFalse(t.raw_complete(file,status),'FINISH_REQUIRES_FINISHED_TRUE')
        finish[-1]['finished']=True;file,status=self.artifact(finish);self.assertTrue(t.raw_complete(file,status),'HTTP_503_IS_METADATA_NOT_CLINICAL_SUCCESS')
        file,status=self.artifact(rows[:-1]);self.assertFalse(t.raw_complete(file,status),'REQUEST_CLOSE_ALONE_IS_NOT_RESPONSE_TERMINAL')
        duplicate=copy.deepcopy(rows);duplicate.append({**rows[-1],'sequence':4});file,status=self.artifact(duplicate);self.assertFalse(t.raw_complete(file,status),'ONCE_PHASE_DUPLICATE')
        for field,value in [('instance','22222222-2222-4222-8222-222222222222'),('pid',2),('headerLsn','0/200'),('idempotency','0/200'),('request',2)]:
            changed=copy.deepcopy(rows);changed[-1][field]=value;file,status=self.artifact(changed);self.assertFalse(t.raw_complete(file,status),'REQUEST_IDENTITY_CONTRACT')
        file,status=self.artifact(self.rows());self.assertTrue(t.raw_complete(file,status),'ABORT_IS_COMPLETE_METADATA_OBSERVATION')
    def test_selected_capture_counts_match_bytes_and_optional_seal(self):
        row={'sequence':1,'phase':'observe-call'};file=self.root/'selected';payload=json.dumps(row)+'\n';file.write_text(payload)
        status={'qualification':'COMPLETE','rows':1,'bytes':len(payload.encode()),'written':1,'pending':0,'dropped':0,'failed':None,'closed':False}
        self.assertTrue(t.selected_complete(file,status))
        self.assertFalse(t.selected_complete(file,{**status,'bytes':0}));self.assertFalse(t.selected_complete(file,{**status,'rows':0,'written':0}))
        seal={'phase':'trace-seal','at':1,'pid':1,**{key:status[key] for key in ('rows','bytes','written','pending','dropped','failed')}};file.write_text(payload+json.dumps(seal)+'\n')
        self.assertFalse(t.selected_complete(file,status));status['closed']=True;self.assertTrue(t.selected_complete(file,status))

class ActualDiscoverySelection(unittest.TestCase):
    def capture(self,load):
        import contextlib,subprocess
        from unittest.mock import patch
        import adapter as a,discovery as d
        from test_discovery import Discovery
        from probe import generate
        fixture=Discovery();folder,m=fixture.setup();self.addCleanup(fixture.doCleanups)
        A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
        m.update(project='owned',port=1234,restartRoles=['api'],settingsFingerprint={'sha256':'a'*64},generator={'tools':{'node':{'path':'node'}}},clinicalTimeline={'targets':{'hotA':A,'comparisonB':B}})
        a.write(folder/'tenants.private.json',[{'id':'a'},{'id':'b'}]);record=d.Record(a,folder,m);captured={}
        class Process:
            pid=12345;returncode=7
            def poll(self):return 7
            def wait(self,timeout):return 7
        def popen(*args,**kwargs):captured.update(kwargs['env']);return Process()
        @contextlib.contextmanager
        def ctx(*args):yield
        def command(argv,**kwargs):a.write(folder/'load/k6-summary.json',{'metrics':{}})
        with contextlib.ExitStack() as stack:
            for name in ('psql','job_record','stop_job','quiet','assert_owned','phase_snapshot'):stack.enter_context(patch.object(a,name))
            stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']));stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
            for name in ('sampling','loadgen_process','observe_progress'):stack.enter_context(patch.object(a,name,ctx))
            stack.enter_context(patch.object(a.subprocess,'Popen',side_effect=popen));stack.enter_context(patch.object(a,'command',side_effect=command));stack.enter_context(patch.object(a,'stored',return_value={}))
            load(a,folder,m,'k6',record)
        probe=folder/'probe.js';generate(a.ROOT,probe)
        result=subprocess.run(['node',str(a.HERE/'clinical-timeline-discovery-client-control.cjs'),str(probe),json.dumps(captured),str(folder/'load')],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
    def test_actual_discovery_env_activates_client_omission_red_restored(self):
        import inspect,discovery as d
        original=d.discovery_load;source=inspect.getsource(original);needle='    env.update(a.clinical_timeline.probe_environment(m))'
        self.assertEqual(source.count(needle),1);namespace=dict(d.__dict__);exec(compile(source.replace(needle,'    pass # deliberate caller omission'),d.__file__,'exec'),namespace);broken=namespace['discovery_load']
        def criterion(value):self.assertTrue(value['active'],'DISCOVERY_CLIENT_TIMELINE_MUST_ACTIVATE');self.assertEqual(value['rows'],2)
        criterion(self.capture(original))
        with self.assertRaisesRegex(AssertionError,'DISCOVERY_CLIENT_TIMELINE_MUST_ACTIVATE'):criterion(self.capture(broken))
        criterion(self.capture(original))

if __name__=='__main__':unittest.main()
