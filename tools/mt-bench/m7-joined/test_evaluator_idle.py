import copy
import json
import unittest
from pathlib import Path
import time
import test_evaluator_progress as fixtures
import evaluator_progress as p
import evaluator_idle as idle
from test_evaluator_progress import A,B,R,S

class Idle(unittest.TestCase):
    def rounds(self,due=1000000,increment=0):
        rounds=[]
        for i,at in enumerate((100000,160000,220000)):
            rows={tenant:{'service':'evaluator','runtimeId':R,'generation':1,'completedAcquisitions':1,'completedTimeCycles':i*increment,'failedCompletions':0,'lastCompletedAgeMs':0,'legacyCycles':1+i*increment,'admitted':True,'ready':True,'code':None,'alert':None,'dueAt':due,'dueReason':None if due is None else 'sgv-recent-10','jobs':dict.fromkeys(idle.FLAGS,False)} for tenant in (A,B)}
            def stamp(offset):return {'wallUs':(at+offset)*1000,'monoBeforeUs':(at+offset)*1000-100,'monoAfterUs':(at+offset)*1000+100}
            rounds.append({'instances':{'evaluator':{'runtimeId':R,'ordinal':0}},'owners':rows,'allRows':{'evaluator':rows},'queries':1,'bytes':100,'wallSeconds':.2,'readWindows':{'evaluator':{'start':stamp(0),'end':stamp(200),'observedAt':[at+100]}}})
        return rounds
    def refuse(self,rounds,code):
        with self.assertRaisesRegex(p.Refused,code):idle.assess(rounds,[A,B])
    def test_quiet_future_and_explicit_no_timer_are_not_work_witnesses(self):
        for due,state in ((1000000,'FUTURE_DUE'),(None,'NO_TIMER_DECLARED')):
            rounds=self.rounds(due);v=idle.assess(rounds,[A,B]);self.assertFalse(v['timeWitness']);self.assertEqual(v['completedTimeDelta'],0)
            self.assertEqual(v['classifications']['TIME_NOT_EXERCISED'],2);self.assertEqual(v['classifications'][state],2)
            self.assertEqual(idle.verify(idle.pack({**v,'rounds':rounds}),2,['evaluator']),v)
            with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(rounds,[A,B],'idle')
    def test_observed_due_requires_actual_later_time_even_if_later_due_moves_future(self):
        for due in (100001,1):
            rounds=self.rounds();rounds[0]['owners'][A]['dueAt']=due;self.refuse(rounds,'TIME_NOT_OBSERVED')
            rounds[1]['owners'][A]['completedTimeCycles']=1;rounds[1]['owners'][A]['legacyCycles']=2
            rounds[2]['owners'][A]['completedTimeCycles']=1;rounds[2]['owners'][A]['legacyCycles']=2
            v=idle.assess(rounds,[A,B]);self.assertEqual(v['classifications']['TIME_EXERCISED'],1);self.assertFalse(v['timeWitness'])
    def test_final_read_bracket_due_ambiguity_is_not_opportunity_proof(self):
        for at in (220050,220000,220201):
            rounds=self.rounds();rounds[-1]['owners'][A]['dueAt']=at
            if at<=220200:self.refuse(rounds,'TIME_NOT_OBSERVED')
            else:self.assertEqual(idle.assess(rounds,[A,B])['verdict'],'PASS')
    def test_earlier_due_inside_final_read_with_actual_completion_is_exercised(self):
        rounds=self.rounds()
        for i in (0,1):rounds[i]['owners'][A].update(dueAt=220050,dueReason='sgv-recent-10')
        rounds[2]['owners'][A].update(completedTimeCycles=1,legacyCycles=2,dueAt=None,dueReason=None)
        value=idle.assess(rounds,[A,B]);self.assertEqual(value['classifications']['TIME_EXERCISED'],1)
        self.assertEqual(value['completedTimeDelta'],1);self.assertFalse(value['timeWitness'])
        packed=idle.pack({**value,'rounds':rounds});self.assertEqual(idle.verify(packed,2,['evaluator']),value)
        old=copy.deepcopy(packed);old['policy']['moduleVersion']=2
        with self.assertRaisesRegex(p.Refused,'IDLE_VERSION'):idle.verify(old,2,['evaluator'])
    def test_crossing_uncompleted_and_final_only_demand_stay_unmeasured(self):
        for due in (220050,220201):
            rounds=self.rounds()
            for i in (0,1):rounds[i]['owners'][A].update(dueAt=due,dueReason='sgv-recent-10')
            rounds[-1]['owners'][A].update(dueAt=None,dueReason=None)
            if due<=220200:self.refuse(rounds,'TIME_NOT_OBSERVED')
            else:self.assertEqual(idle.assess(rounds,[A,B])['verdict'],'PASS')
        rounds=self.rounds();rounds[0]['owners'][A]['dueAt']=1
        rounds[-1]['owners'][A].update(dueAt=220050,completedTimeCycles=1,legacyCycles=2)
        self.refuse(rounds,'TIME_NOT_OBSERVED') # positive earlier work does not cover final-only demand
    def test_all_clinical_slots_and_explicit_null_pending_refuse(self):
        for key in idle.FLAGS:
            for due in (1000000,None):
                rounds=self.rounds(due);rounds[1]['owners'][A]['jobs'][key]=True;self.refuse(rounds,'JOB_PENDING')
        for value in (None,{},dict.fromkeys(idle.FLAGS,0)):
            rounds=self.rounds();rounds[0]['owners'][A]['jobs']=value;self.refuse(rounds,'IDLE_JOBS')
    def test_positive_time_progress_with_any_pending_clinical_slot_is_busy_unmeasured(self):
        for flag in idle.FLAGS:
            rounds=self.rounds();rounds[0]['owners'][A]['dueAt']=1
            for step in (1,2):rounds[step]['owners'][A].update(completedTimeCycles=step,legacyCycles=step+1)
            self.assertEqual(idle.assess(rounds,[A,B])['classifications']['TIME_EXERCISED'],1)
            rounds[1]['owners'][A]['jobs'][flag]=True
            with self.assertRaisesRegex(p.Refused,'JOB_PENDING') as caught:idle.assess(rounds,[A,B])
            self.assertEqual(caught.exception.verdict,'UNMEASURED')
            self.assertEqual(rounds[-1]['owners'][A]['completedTimeCycles'],2,'BUSY_DOES_NOT_ERASE_SUCCESSFUL_COMPLETION')
    def test_failures_resets_new_demand_foreign_and_unhealthy_cannot_be_quiet(self):
        for field,value,code in [('failedCompletions',1,'HIDDEN_FAILURE'),('generation',2,'RESET'),('completedAcquisitions',2,'NEW_DEMAND'),('ready',False,'ERROR'),('code','EVALUATOR_WINDOW_REFUSED','ERROR')]:
            rounds=self.rounds();rounds[1]['owners'][A][field]=value;self.refuse(rounds,code)
        rounds=self.rounds();rounds[-1]['owners'][A]['legacyCycles']=2;self.refuse(rounds,'UNCREDITED_WORK')
        rounds=self.rounds();rounds[1]['instances']['evaluator']['runtimeId']=S;self.refuse(rounds,'RESET')
        rounds=self.rounds();rounds[1]['allRows']['evaluator'].pop(A);self.refuse(rounds,'COVERAGE')
    def test_malformed_due_and_missing_legacy_are_not_explicit_null(self):
        for value in (False,float('nan'),float('inf'),-1):
            rounds=self.rounds();rounds[1]['owners'][A]['dueAt']=value;self.refuse(rounds,'DUE_CONTRACT')
        rounds=self.rounds();del rounds[1]['owners'][A]['dueAt'];self.refuse(rounds,'DUE_CONTRACT')
        old=p.pack({**p.assess(self.rounds(increment=1),[A,B],'idle'),'rounds':self.rounds(increment=1)})
        with self.assertRaisesRegex(p.Refused,'IDLE_VERSION'):idle.verify(old,2,['evaluator'])
    def test_clock_missing_wall_jump_helper_outside_or_round_overlap_refuses(self):
        rounds=self.rounds();del rounds[0]['readWindows'];self.refuse(rounds,'IDLE_CLOCK')
        rounds=self.rounds();rounds[-1]['readWindows']['evaluator']['end']['wallUs']+=1000000;self.refuse(rounds,'IDLE_CLOCK')
        rounds=self.rounds();rounds[0]['readWindows']['evaluator']['observedAt']=[1];self.refuse(rounds,'IDLE_CLOCK')
        rounds=self.rounds();rounds[-1]['readWindows']=copy.deepcopy(rounds[0]['readWindows']);self.refuse(rounds,'IDLE_CLOCK')
    def test_all_foreign_rows_retained_and_no_hidden_work_or_pending_job(self):
        rounds=self.rounds()
        for raw in rounds:
            raw['instances']['evaluator-2']={'runtimeId':S,'ordinal':1}
            rows=copy.deepcopy(raw['allRows']['evaluator'])
            for row in rows.values():row.update(service='evaluator-2',runtimeId=S,admitted=False,ready=False,completedAcquisitions=0,legacyCycles=0,lastCompletedAgeMs=None,dueAt=None,dueReason=None)
            raw['allRows']['evaluator-2']=rows;raw['readWindows']['evaluator-2']=copy.deepcopy(raw['readWindows']['evaluator']);raw['queries']=2
        self.assertEqual(idle.assess(rounds,[A,B])['verdict'],'PASS')
        broken=copy.deepcopy(rounds);broken[1]['allRows']['evaluator-2'][A]['legacyCycles']=1;self.refuse(broken,'FOREIGN')
        broken=copy.deepcopy(rounds);broken[1]['allRows']['evaluator-2'][A]['jobs']['acquire']=True;self.refuse(broken,'FOREIGN_PENDING')
        broken=copy.deepcopy(rounds);broken[1]['allRows']['evaluator-2'].pop(B);self.refuse(broken,'COVERAGE')
    def test_actual_read_brackets_and_selected_metadata_use_no_additional_fetches(self):
        count=0
        def fetch(*args):
            nonlocal count
            count+=1;frame=fixtures.Progress().frame()
            frame['observedAt']=int(time.time()*1000)
            for row in frame['view']['tenants']:row['jobs']=dict.fromkeys(idle.FLAGS,False)
            return json.dumps(frame).encode()+b'\n'
        value=idle.round_view(['evaluator'],[A,B],fetch);self.assertEqual(count,1)
        self.assertEqual(value['queries'],1);idle.clock_windows([value])
        self.assertTrue(all(not any(row['jobs'].values()) for row in value['owners'].values()))
    def test_missing_opportunity_or_job_guards_produces_false_pass_then_restored_refuses(self):
        source=Path(idle.__file__).read_text()
        for needle,broken in [("last['completedTimeCycles']>rows[i]['completedTimeCycles']",'True'),("not any(jobs(row['jobs']).values())",'True')]:
            namespace={'__name__':'owned_idle_mutant'};exec(compile(source.replace(needle,broken),'owned_idle_mutant','exec'),namespace)
            rounds=self.rounds()
            if 'completedTimeCycles' in needle:rounds[0]['owners'][A]['dueAt']=1
            else:rounds[1]['owners'][A]['jobs']['running']=True
            with self.assertRaises(p.Refused):idle.assess(rounds,[A,B])
            self.assertEqual(namespace['assess'](rounds,[A,B])['verdict'],'PASS','CONTROL_EXPOSES_FALSE_PASS')
            with self.assertRaises(p.Refused):idle.assess(rounds,[A,B])
    def test_packed_recomputation_and_bool_slot_tamper(self):
        rounds=self.rounds();v=idle.pack({**idle.assess(rounds,[A,B]),'rounds':rounds});v['rounds'][0]['rows'][0][-1]=False
        with self.assertRaisesRegex(p.Refused,'IDLE_JOBS'):idle.verify(v,2,['evaluator'])
        v=idle.pack({**idle.assess(rounds,[A,B]),'rounds':rounds});v['classifications']['TIME_EXERCISED']=1
        with self.assertRaisesRegex(p.Refused,'ASSESSMENT'):idle.verify(v,2,['evaluator'])

if __name__=='__main__':unittest.main()
