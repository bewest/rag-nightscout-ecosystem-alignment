"""Explicit timing failures stay findings; structural/identity failures refuse."""
import ast
import copy
from pathlib import Path
import unittest
import discovery
import evaluator_idle as idle
import evaluator_progress as progress
import test_discovery as producer
import test_evaluator_idle as idle_fixtures
from test_evaluator_idle import A,B,R,S

# Exhaustive current source inventory: a new code requires a deliberate audit.
HARD=set('''IDLE_ASSESSMENT IDLE_CLOCK IDLE_FOREIGN_PENDING IDLE_JOBS IDLE_PHASE PROGRESS_ROUNDS
IDLE_TAIL_COVERAGE IDLE_TAIL_QUERY_BOUND IDLE_TAIL_UNEXPECTED IDLE_VERSION
PROGRESS_ASSESSMENT PROGRESS_BODY_FAILED PROGRESS_BUDGET PROGRESS_BYTE_BOUND
PROGRESS_COLUMNS PROGRESS_CONTRACT PROGRESS_COVERAGE PROGRESS_DUE_CONTRACT
PROGRESS_FOREIGN PROGRESS_GATE PROGRESS_INSTANCE PROGRESS_INSTANCE_BOUND
PROGRESS_OVERHEAD PROGRESS_PROOF PROGRESS_QUERY_BOUND PROGRESS_RESET
PROGRESS_RESPONSE PROGRESS_RESPONSE_BOUND PROGRESS_SELECTOR PROGRESS_TENANTS'''.split())
HARD={'M7_EVALUATOR_'+code for code in HARD}

class Classification(unittest.TestCase):
    def error(self,fn):
        try:fn()
        except progress.Refused as error:return error
        self.fail('actual source predicate did not refuse')
    def raw_shape(self):
        rows=idle_fixtures.Idle().rounds(due=1)
        rows[-1]['owners'][A]['jobs']['running']=True
        return rows
    def produce(self,error):
        fixture=producer.Discovery();self.addCleanup(fixture.doCleanups)
        return fixture.run_recording(error)
    def test_actual_tail_opportunity_unmeasured_producer_continues_load_and_preserves_finding(self):
        rows=self.raw_shape();idle.stability(rows,[A,B]);idle.clock_windows(rows)
        error=self.error(lambda:idle.assess(rows,[A,B]));self.assertEqual((str(error),error.verdict),('M7_EVALUATOR_IDLE_TAIL_OPPORTUNITY','UNMEASURED'))
        result,calls,_=self.produce(error);self.assertEqual(calls,['load']);self.assertEqual(result['strictChecks']['idle'],{'verdict':'UNMEASURED','code':str(error),'hardFailure':False});self.assertEqual(result['capacityAcceptance'],'NOT_GRANTED')
    def test_actual_missing_midpoint_needs_valid_partial_capture_before_continuation(self):
        fixture=producer.Discovery();self.addCleanup(fixture.doCleanups);folder,m=fixture.setup()
        # Actual source proof and actual summary producer, with no SQL/resources.
        expected=[{'id':A},{'id':B}];producer.a.write(folder/'tenants.private.json',expected)
        rows=idle_fixtures.Idle().rounds()[:2]
        error=self.error(lambda:progress.assess(rows,[A,B],'load'))
        raw=progress.pack({'phase':'load','verdict':'UNMEASURED','code':str(error),'policy':progress.POLICY,'attribution':producer.a.progress_attribution(m),'rounds':rows})
        file=folder/'load/evaluator-progress.json';producer.a.write(file,raw)
        from unittest.mock import patch
        def produce(value):
            producer.a.write(file,value);record=discovery.Record(producer.a,folder,m)
            with patch.object(producer.a,'progress_services',return_value=['evaluator']):record.observe('load',lambda:(_ for _ in ()).throw(error))
            return record.value
        result=produce(raw);self.assertFalse(result['strictChecks']['load']['hardFailure']);self.assertEqual(result['strictChecks']['load']['partialObservation']['rounds'],2)
        for mutate in (lambda v:v.update(phase='wrong'),lambda v:v.update(rounds=v['rounds']*2),lambda v:v.update(rounds=[]),lambda v:v['attribution'].update(instrument='0'*64),lambda v:v['rounds'][1]['instances']['evaluator'].update(runtimeId=S),lambda v:v['rounds'][1].update(bytes=progress.POLICY['maxBytesPerPhase']+1),lambda v:v['rounds'][1]['rows'][0].__setitem__(progress.COLUMNS.index('admitted'),False)):
            broken=copy.deepcopy(raw);mutate(broken)
            with self.assertRaises(Exception):produce(broken)
        self.assertFalse(produce(raw)['strictChecks']['load']['hardFailure'])
        idle_raw=idle.pack({'phase':'idle','verdict':'UNMEASURED','code':str(error),'policy':idle.POLICY,'attribution':producer.a.progress_attribution(m),'rounds':rows})
        idle_file=folder/'idle/evaluator-progress.json';producer.a.write(idle_file,idle_raw)
        with patch.object(producer.a,'progress_services',return_value=['evaluator']):
            record=discovery.Record(producer.a,folder,m);record.observe('idle',lambda:(_ for _ in ()).throw(error));self.assertFalse(record.value['strictChecks']['idle']['hardFailure'])
            broken=copy.deepcopy(idle_raw);broken['rounds'][1]['readWindows']['evaluator']['end']['wallUs']+=10000;producer.a.write(idle_file,broken)
            with self.assertRaisesRegex(progress.Refused,'CLOCK'):record.observe('idle',lambda:(_ for _ in ()).throw(error))
    def test_all_current_typed_codes_have_explicit_discovery_classification(self):
        codes=set()
        for module in (idle,progress):
            codes.update(n.value for n in ast.walk(ast.parse(Path(module.__file__).read_text())) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('M7_') and n.value.replace('_','').isalnum())
        self.assertEqual(codes,HARD|(discovery.INCOMPLETE&codes)|discovery.SOFT_WORK_FAILURES)
        for code in codes:
            expected=code not in HARD
            self.assertEqual(discovery.incomplete(progress.Refused(code)),expected,code)
            # Only the two separately adopted work-failure counters are soft
            # under FAIL; timing/availability codes are soft only when UNMEASURED.
            self.assertEqual(discovery.incomplete(progress.Refused(code,'FAIL')),code in discovery.SOFT_WORK_FAILURES,code)
        self.assertFalse(discovery.incomplete(progress.Refused('M7_UNKNOWN_FUTURE_CODE')))
    def test_actual_clock_reset_coverage_and_foreign_controls_still_stop_before_load(self):
        cases=[]
        rows=self.raw_shape();rows[-1]['readWindows']['evaluator']['end']['wallUs']+=10000;cases.append(('CLOCK',rows))
        rows=self.raw_shape();rows[1]['owners'][A]['generation']+=1;cases.append(('RESET',rows))
        rows=self.raw_shape();rows[1]['owners'].pop(B);cases.append(('COVERAGE',rows))
        rows=self.raw_shape()
        for current in rows:
            current['instances']['other']={'runtimeId':S,'ordinal':1}
            current['allRows']['other']={tenant:{**copy.deepcopy(row),'admitted':False,'ready':False,'completedAcquisitions':0,'completedTimeCycles':0,'legacyCycles':0,'jobs':dict.fromkeys(idle.FLAGS,False)} for tenant,row in current['owners'].items()}
            current['readWindows']['other']=copy.deepcopy(current['readWindows']['evaluator'])
        rows[-1]['allRows']['other'][A]['completedTimeCycles']=1;cases.append(('FOREIGN',rows))
        for code,rows in cases:
            with self.subTest(code=code):
                error=self.error(lambda:idle.assess(rows,[A,B]));self.assertIn(code,str(error));result,calls,_=self.produce(error);self.assertEqual(calls,[]);self.assertTrue(result['hardFailures'])
        for code in ('M7_EVALUATOR_IDLE_TAIL_OPPORTUNITY','M7_EVALUATOR_PROGRESS_ROUNDS'):
            result,calls,_=self.produce(progress.Refused(code,'FAIL'));self.assertEqual(calls,[]);self.assertTrue(result['hardFailures'])

if __name__=='__main__':unittest.main()
