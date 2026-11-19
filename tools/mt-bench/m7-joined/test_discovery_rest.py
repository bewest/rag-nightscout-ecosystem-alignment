"""Synthetic semantic controls for REST alongside one explicit clinical failure."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import adapter as a
import discovery
import discovery_rest as r
import evaluator_progress as p
import evaluator_opportunities as o
import test_evaluator_progress as progress_fixture
import test_evaluator_opportunities as opportunity_fixture
A,B=progress_fixture.A,progress_fixture.B

class RestAlongsideClinicalStall(unittest.TestCase):
    def manifest(self):return {'runPurpose':'discovery','profile':'pgstream-sample','evaluatorOpportunities':'received-input-v1','owner':'f'*32,'pair':opportunity_fixture.BINDING['pair'],'imageId':opportunity_fixture.BINDING['imageId'],'instrument':{'sha256':opportunity_fixture.BINDING['instrument']}}
    def frame(self):
        frame=progress_fixture.Progress().frame();row=frame['view']['tenants'][0]
        row.update(ready=False,code=r.CODE,jobs=dict.fromkeys(p.JOB_FLAGS,False));row['jobs']['running']=True
        row['progress'].update(completedAcquisitions=1,failedCompletions=0,lastCompletedAgeMs=41175)
        return frame
    def test_real_readiness_retains_clinical_fail_and_allows_only_discovery(self):
        frame=self.frame();m=self.manifest()
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);a.write(d/'tenants.private.json',[{'id':A},{'id':B}])
            with patch.object(a,'progress_services',return_value=['evaluator']),patch.object(a,'progress_fetch',return_value=json.dumps(frame)),patch.object(a.time,'sleep'):
                finding=a.readiness(d,m)
            self.assertTrue(r.result(finding));self.assertEqual(finding['capacityAcceptance'],'NOT_GRANTED');self.assertTrue(r.permitted(a,d,m))
            self.assertEqual(a.document(d/'runtime-readiness.json')['clinicalVerdict'],'FAIL')
            changed=copy.deepcopy(m);changed['instrument']['sha256']='0'*64
            with self.assertRaisesRegex(p.Refused,'BINDING'):r.permitted(a,d,changed)
        with self.assertRaisesRegex(p.Refused,'ERROR'):p.round_view(['evaluator'],[A,B],lambda *_:json.dumps(frame),warming=True,allow_unavailable=True)
        self.assertFalse(r.selected({**m,'runPurpose':'acceptance'}))
    def test_other_errors_alerts_malformed_jobs_and_partial_roster_still_refuse(self):
        cases=[lambda f:f['view']['tenants'][0].update(code='EVALUATOR_RESTORE_CHANGED'),lambda f:f['view']['tenants'][0].update(evaluation={'alert':'unknown'}),lambda f:f['view']['tenants'][0]['jobs'].update(running='true'),lambda f:f['view']['tenants'].pop(),lambda f:f['view']['gate'].update(eligible=False)]
        for change in cases:
            frame=self.frame();change(frame)
            with self.assertRaises(p.Refused):p.round_view(['evaluator'],[A,B],lambda *_:json.dumps(frame),warming=True,allow_unavailable=True,allow_clinical_stall=True)
    def inputs(self):
        f=opportunity_fixture.Opportunities();rounds=f.rounds();captures=f.captures()
        for point in rounds:
            row=point['owners'][A];row.update(ready=False,code=r.CODE,lastCompletedAgeMs=41175)
            row['jobs']['running']=True;row['jobState']=dict(row['jobs'])
        return rounds,captures
    def verdict(self,rounds,captures):return r.assess_rest(rounds,[A,B],'load',captures,opportunity_fixture.BINDING)
    def test_clinical_never_passes_and_durable_restore_foreign_clock_reset_stay_hard(self):
        rounds,captures=self.inputs();self.assertTrue(r.result(self.verdict(rounds,captures)))
        cases=[lambda x,y:y[-1]['rows'][0].update(restoreGeneration='1'),lambda x,y:y[-1].update(reader={}),lambda x,y:x[-1]['instances']['evaluator'].update(runtimeId='99999999-9999-4999-8999-999999999999'),lambda x,y:x[-1]['owners'][A].update(completedAcquisitions=0),lambda x,y:x[-1]['readWindows']['evaluator']['end'].update(wallUs=0)]
        for change in cases:
            x,y=copy.deepcopy((rounds,captures));change(x,y)
            with self.assertRaises(p.Refused):self.verdict(x,y)
        with patch.object(r,'assess_rest',return_value={'verdict':'PASS'}):
            self.assertFalse(r.result(r.assess_rest(rounds,[A,B],'load',captures,opportunity_fixture.BINDING)))
        self.assertEqual(self.verdict(rounds,captures)['clinicalVerdict'],'FAIL')
    def artifact(self):
        rounds,captures=self.inputs();written=[]
        observer=o.Observer(['evaluator'],[A,B],lambda *_:None,1,'load',written.append,durable_fetch=lambda:None,binding=opportunity_fixture.BINDING,preparation_cost={'nodeCalls':1,'sqlQueries':0,'wallSeconds':0,'observerProcessCpuSeconds':0},source_sha256='a'*64,query_sha256='b'*64)
        observer.rest_only=True;observer.rounds=rounds;observer.durable=captures
        observer.windows=[{'startNs':i*1000000000,'durableEndNs':i*1000000000+100000000,'inspectionEndNs':i*1000000000+200000000} for i in range(3)]
        observer.costs=[{'sqlQueries':1,'nodeCalls':1,'rawSqlBytes':1,'wallSeconds':.01,'observerProcessCpuSeconds':0} for _ in range(3)]
        observer.finish();return o.pack(written[0])
    def test_actual_durable_observer_publishes_verified_clinical_failure(self):
        def criterion():
            value=self.artifact();self.assertTrue(r.result(value));return value
        artifact=criterion()
        broken={**self.verdict(*self.inputs()),'verdict':'PASS'}
        with patch.object(r,'assess_rest',return_value=broken):
            with self.assertRaises(AssertionError):criterion()
        criterion()
        self.assertTrue(r.result(o.verify(artifact,2,['evaluator'],opportunity_fixture.BINDING)))
        bad=copy.deepcopy(artifact);bad['durable'][-1]['rows'][0]['restoreGeneration']='1'
        with self.assertRaises(p.Refused):o.verify(bad,2,['evaluator'],opportunity_fixture.BINDING)
        bad=copy.deepcopy(artifact);bad['verdict']='PASS'
        with self.assertRaisesRegex(p.Refused,'ASSESSMENT'):o.verify(bad,2,['evaluator'],opportunity_fixture.BINDING)
        self.assertTrue(r.result(o.verify(artifact,2,['evaluator'],opportunity_fixture.BINDING)))
    def test_remote_idle_and_summary_keep_clinical_failure_with_rest_metrics(self):
        import sys
        sys.path.insert(0,str(a.HERE.parent/'remote-pgstream'))
        import app
        m=self.manifest();m.update(tenants=2,cadence={'warmupSeconds':0,'idleSeconds':0})
        finding={'verdict':'FAIL','clinicalVerdict':'FAIL','clinicalCode':r.CODE,'restCollectionPermitted':True}
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            with patch.object(a,'frozen'),patch.object(a,'quiet'),patch.object(a,'verify'),patch.object(a,'readiness',return_value=finding),patch.object(a,'psql'),patch.object(a,'phase_snapshot'),patch.object(a,'enabled_idle',return_value=types.SimpleNamespace(result=finding)),patch.object(app.time,'sleep'):
                self.assertEqual(app.idle(d,m),finding)
            out=d/'load';out.mkdir();(out/'runid').write_text('synthetic');(d/'idle/evaluator-progress.json').write_text(json.dumps(self.artifact()))
            with patch.object(a,'verify'),patch.object(app,'load'),patch.object(a,'progress_services',return_value=['evaluator']),patch.object(discovery,'count_observation',return_value=({'verdict':'GREEN'},True)),patch('clinical.completed',return_value={'verdict':'UNMEASURED'}),patch.object(app,'measurements',return_value={}):
                result=app.discovery_summary(d,m,{}, {},{'metrics':{'http_reqs':{'count':3}}})
            self.assertEqual(result['clinicalVerdict'],'FAIL');self.assertEqual(result['metrics']['http_reqs']['count'],3);self.assertEqual(result['capacityAcceptance'],'NOT_GRANTED');self.assertEqual(result['strictChecks']['idle']['verdict'],'FAIL')
    def test_independent_work_runs_and_record_keeps_fail(self):
        rounds,captures=self.inputs();finding=self.verdict(rounds,captures);calls=[]
        class Observer:
            result=finding
            def __enter__(self):calls.append('fenced-enter');return self
            def __exit__(self,*_):calls.append('fenced-exit')
        with patch.object(a,'observe_progress',return_value=Observer()):
            result=discovery.observed_load(a,Path('/synthetic'),{},Path('/synthetic/load'),lambda:calls.append('REST'))
        self.assertEqual(calls,['fenced-enter','REST','fenced-exit']);self.assertTrue(r.result(result))
        # Exercise the actual record producer without constructing another fixture.
        record=object.__new__(discovery.Record);record.m=self.manifest();record.value={'strictChecks':{},'capacityAcceptance':'NOT_GRANTED'};record.save=lambda:None
        record.observe('load',lambda:result)
        self.assertEqual(record.value['clinicalVerdict'],'FAIL');self.assertEqual(record.value['strictChecks']['load']['verdict'],'FAIL');self.assertFalse(record.value['strictChecks']['load']['hardFailure'])
        with patch.object(a,'observe_progress',side_effect=p.Refused('M7_OPPORTUNITY_BINDING','FAIL')):
            with self.assertRaises(p.Refused):discovery.observed_load(a,Path('/synthetic'),{},Path('/synthetic/load'),lambda:calls.append('MUST_NOT_RUN'))
        self.assertNotIn('MUST_NOT_RUN',calls)


    def test_idle_known_clinical_stall_retains_fail_with_red_restored_control(self):
        # Shape reproduced at local1000 readiness: admitted, one completed
        # acquisition, explicit stall, all six jobs false, no failed completions.
        frame=self.frame()
        row=frame['view']['tenants'][0]
        row['jobs']=dict.fromkeys(p.JOB_FLAGS,False)
        row['progress'].update(completedAcquisitions=1,failedCompletions=0,lastCompletedAgeMs=2170)
        def criterion():
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);a.write(d/'tenants.private.json',[{'id':A},{'id':B}])
                with patch.object(a,'progress_services',return_value=['evaluator']),patch.object(a,'progress_fetch',return_value=json.dumps(frame)),patch.object(a.time,'sleep'):
                    finding=a.readiness(d,self.manifest())
                self.assertTrue(r.result(finding))
                self.assertEqual(finding['clinicalVerdict'],'FAIL')
                self.assertEqual(finding['capacityAcceptance'],'NOT_GRANTED')
                return finding
        criterion()
        selected=p.clinical_stall
        with patch.object(p,'clinical_stall',side_effect=lambda value:selected(value) and value['jobState']['running']):
            with self.assertRaisesRegex(p.Refused,'M7_EVALUATOR_PROGRESS_ERROR'):criterion()
        criterion()
        for change in (lambda value:value.update(code='EVALUATOR_RESTORE_CHANGED'),
                       lambda value:value.update(evaluation={'alert':'unknown'}),
                       lambda value:value['jobs'].update(running='false')):
            broken=copy.deepcopy(frame);change(broken['view']['tenants'][0])
            with self.assertRaises(p.Refused):
                p.round_view(['evaluator'],[A,B],lambda *_:json.dumps(broken),warming=True,allow_unavailable=True,allow_clinical_stall=True)
        print('IDLE_CLINICAL_STALL busy-bit representation RED; clinical FAIL retained; RESTORED_GREEN')

if __name__=='__main__':unittest.main()
