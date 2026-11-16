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
if __name__=='__main__':unittest.main()
