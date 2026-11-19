"""Synthetic collection controls. No app, database, Docker or network activity."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import evaluator_progress as p
import adapter
import test_evaluator_progress as fixtures
A=fixtures.A

class Warming(unittest.TestCase):
    def frame(self):
        frame=fixtures.Progress().frame(ids=[A]);row=frame['view']['tenants'][0]
        row['progress'].update(completedAcquisitions=0,completedTimeCycles=0,failedCompletions=0,lastCompletedAgeMs=None)
        return frame
    def collect(self,frame,warming=True):
        return p.round_view(['evaluator'],[A],lambda *_:json.dumps(frame).encode(),warming=warming)
    def test_first_release_is_warming_without_completion_credit(self):
        value=self.collect(self.frame());self.assertIsNone(value['owners'][A]['lastCompletedAgeMs'])
        self.assertEqual(value['owners'][A]['completedAcquisitions'],0)
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess([value]*3,[A],'idle')
        with self.assertRaisesRegex(p.Refused,'CONTRACT'):self.collect(self.frame(),warming=False)
    def test_nonzero_counters_or_invalid_age_are_not_first_admission(self):
        for key,value in [('completedAcquisitions',1),('completedTimeCycles',1),('lastCompletedAgeMs',False),('lastCompletedAgeMs',-1),('lastCompletedAgeMs','0'),('lastCompletedAgeMs',float('nan'))]:
            frame=self.frame();frame['view']['tenants'][0]['progress'][key]=value
            with self.subTest(key=key,valueType=type(value).__name__),self.assertRaisesRegex(p.Refused,'CONTRACT'):self.collect(frame)
    def test_uncredited_attempt_is_observed_but_earns_no_healthy_progress(self):
        # c621 separates historical uncredited attempts from earned work.
        frame=self.frame();frame['view']['tenants'][0]['progress']['failedCompletions']=1
        observed=self.collect(frame);self.assertEqual(observed['owners'][A]['failedCompletions'],1)
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess([observed]*3,[A],'load')

    def test_missing_fields_and_bad_status_still_refuse(self):
        for field in ('generation','completedAcquisitions','completedTimeCycles','failedCompletions','lastCompletedAgeMs'):
            frame=self.frame();del frame['view']['tenants'][0]['progress'][field]
            with self.subTest(field=field),self.assertRaisesRegex(p.Refused,'CONTRACT'):self.collect(frame)
        for change in ({'ready':False},{'code':'EVALUATOR_WINDOW_REFUSED'},{'evaluation':{'alert':'synthetic'}}):
            frame=self.frame();frame['view']['tenants'][0].update(change)
            with self.assertRaisesRegex(p.Refused,'ERROR'):self.collect(frame)
    def test_diagnostics_retain_bounded_whitelist_and_exclude_arbitrary_values(self):
        frame=self.frame();del frame['view']['tenants'][0]['progress']['lastCompletedAgeMs']
        frame['view']['tenants'][0]['privateSyntheticMarker']='must-not-publish'
        with self.assertRaises(p.Refused) as caught:self.collect(frame)
        cost=caught.exception.collection
        self.assertEqual(cost['queries'],1);self.assertTrue(cost['completeResponses'])
        self.assertEqual({k:v for k,v in cost['diagnostic'].items() if k!='failedRow'},{'predicate':'FIELD_REQUIRED','field':'lastCompletedAgeMs','instanceIndex':0,'pageIndex':0,'rowIndex':0,'warming':True})
        row=cost['diagnostic']['failedRow'];self.assertEqual(row['tenant'],A)
        self.assertEqual(row['progress']['lastCompletedAgeMs'],{'type':'missing'})
        self.assertLessEqual(len(json.dumps(row).encode()),p.REFUSAL_ROW_MAX_BYTES)
        self.assertNotIn('must-not-publish',json.dumps(cost))
    def test_existing_job_flags_survive_health_failure_without_arbitrary_job_data(self):
        frame=self.frame();row=frame['view']['tenants'][0]
        row.update(code='EVALUATOR_CLINICAL_PENDING')
        flags=dict.fromkeys(('running','booting','acquire','time','parentAcquire','parentTime'),False)
        flags.update(running=True,parentAcquire=True)
        row['jobs']={**flags,'privateSyntheticMarker':'must-not-retain'}
        # c621 validates the fixed job schema before health; arbitrary job keys
        # are a contract refusal, while the bounded diagnostic retains six flags.
        with self.assertRaisesRegex(p.Refused,'CONTRACT') as caught:self.collect(frame)
        self.assertEqual(caught.exception.verdict,'FAIL')
        diagnostic=caught.exception.collection['diagnostic']['failedRow']
        self.assertEqual(diagnostic['jobs'],flags)
        self.assertNotIn('must-not-retain',json.dumps(diagnostic))
        self.assertLessEqual(len(json.dumps(diagnostic).encode()),p.REFUSAL_ROW_MAX_BYTES)
        def criterion():
            self.assertEqual(p._refusal_row(row,'evaluator',A)['jobs'],flags)
        criterion()
        real=p._refusal_row
        def omit_jobs(*args):
            value=real(*args);value.pop('jobs');return value
        with patch.object(p,'_refusal_row',side_effect=omit_jobs):
            with self.assertRaises(KeyError):criterion()
        criterion()

    def test_remaining_contract_diagnostics_keep_predicate_and_actual_bounded_row(self):
        for field,value in [('cycles',False),('admitted','true'),('ready',0)]:
            frame=self.frame();frame['view']['tenants'][0][field]=value
            with self.assertRaisesRegex(p.Refused,'CONTRACT') as caught:self.collect(frame)
            self.assertEqual(caught.exception.collection['diagnostic']['field'],field)
            self.assertEqual(caught.exception.collection['diagnostic']['failedRow']['tenant'],A)
        for warming in (False,True):
            for field,change,predicate in [('ready',{'ready':False},'OWNER_READY_REQUIRED'),('code',{'code':'PRIVATE_SYNTHETIC_MARKER'},'OWNER_CODE_NULL_REQUIRED'),('evaluation.alert',{'evaluation':{'alert':'PRIVATE_SYNTHETIC_MARKER'}},'OWNER_ALERT_NULL_REQUIRED')]:
                frame=self.frame();frame['view']['tenants'][0].update(change)
                with self.assertRaisesRegex(p.Refused,'ERROR') as caught:self.collect(frame,warming)
                self.assertEqual(caught.exception.verdict,'FAIL')
                self.assertEqual(caught.exception.collection['diagnostic']['field'],field)
                self.assertEqual(caught.exception.collection['diagnostic']['predicate'],predicate)
                row=caught.exception.collection['diagnostic']['failedRow']
                self.assertEqual(row['tenant'],A)
                if field=='code':self.assertEqual(row['code'],'PRIVATE_SYNTHETIC_MARKER')
                if field=='evaluation.alert':self.assertEqual(row['alert'],'PRIVATE_SYNTHETIC_MARKER')
                self.assertLessEqual(len(json.dumps(row).encode()),p.REFUSAL_ROW_MAX_BYTES)
    def test_actual_readiness_allows_first_release_and_keeps_failure_fatal(self):
        held=self.frame();released=copy.deepcopy(held);released['view']['tenants'][0]['progress'].update(completedAcquisitions=1,lastCompletedAgeMs=0)
        records=[];frames=iter([held,released])
        with tempfile.TemporaryDirectory() as directory,patch.object(adapter,'document',return_value=[{'id':A}]),patch.object(adapter,'progress_services',return_value=['evaluator']),patch.object(adapter,'progress_fetch',side_effect=lambda *_, timeout:json.dumps(next(frames)).encode()),patch.object(adapter,'write',side_effect=lambda _,value:records.append(value)),patch.object(adapter.time,'sleep') as sleep:
            adapter.readiness(Path(directory),{})
        sleep.assert_not_called()
        self.assertEqual(records[-1]['verdict'],'PASS')
        self.assertEqual(len(records[-1]['observations']),1)
        released['view']['tenants'][0]['progress']['failedCompletions']=1
        with tempfile.TemporaryDirectory() as directory,patch.object(adapter,'document',return_value=[{'id':A}]),patch.object(adapter,'progress_services',return_value=['evaluator']),patch.object(adapter,'progress_fetch',return_value=json.dumps(released).encode()),patch.object(adapter,'write'),patch.object(adapter.time,'sleep') as sleep:
            with self.assertRaises(p.Refused) as caught:adapter.readiness(Path(directory),{})
            self.assertEqual(caught.exception.verdict,'FAIL');sleep.assert_not_called()
    @unittest.skipUnless(os.environ.get('M7_PROGRESS_CORE') and os.environ.get('M7_PROGRESS_COMMIT'),'exact source recording fixture not selected')
    def test_actual_runtime_window_release_old_new_restore(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('evaluator-readiness-fixture.cjs'))],capture_output=True,check=True,timeout=20)
        value=json.loads(result.stdout);held,released=value['before'],value['after']
        self.assertEqual(held['view']['tenants'][0]['progress']['completedAcquisitions'],0)
        self.assertEqual(self.collect(held)['owners'][A]['completedAcquisitions'],0)
        self.assertEqual(self.collect(released)['owners'][A]['completedAcquisitions'],1)
        source=subprocess.check_output(['git','show','df18100cf13780cec904a792b2bb1ab8867bfb54:tools/mt-bench/m7-joined/evaluator_progress.py'],cwd=Path(__file__).resolve().parents[3],text=True)
        namespace={'__name__':'immutable_previous_collector'};exec(compile(source,'immutable_previous_collector','exec'),namespace)
        for _ in range(2):
            with self.assertRaisesRegex(namespace['Refused'],'M7_EVALUATOR_PROGRESS_CONTRACT'):namespace['round_view'](['evaluator'],[A],lambda *_:json.dumps(held).encode(),warming=True)
        with self.assertRaisesRegex(p.Refused,'CONTRACT'):self.collect(held,warming=False)

if __name__=='__main__':unittest.main()
