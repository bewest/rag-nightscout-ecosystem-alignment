"""Prospective point-tail admission; never retroactively qualifies D."""
import copy
import json
import unittest
from unittest.mock import patch
import evaluator_idle as idle
import evaluator_progress as p
import test_evaluator_idle as idle_fixtures
from test_evaluator_idle import A,B,R,S

class Tail(unittest.TestCase):
    def rounds(self):
        rows=idle_fixtures.Idle().rounds()
        for i in (0,1):rows[i]['owners'][A].update(dueAt=220050,dueReason='sgv-recent-10')
        rows[-1]['owners'][A].update(legacyCycles=2,dueAt=None,dueReason=None)
        rows[-1]['owners'][A]['jobs']['running']=True
        return rows
    def point(self,rounds=None):
        rounds=rounds or self.rounds();point=copy.deepcopy(rounds[-1])
        for service,rows in point['allRows'].items():
            rows.pop(B,None)
            for row in rows.values():
                row['jobs']=dict.fromkeys(idle.FLAGS,False)
                if row['admitted']:row['completedTimeCycles']+=1
        point['owners']={A:point['allRows']['evaluator'][A]}
        point['queries']=len(point['instances'])
        for window in point['readWindows'].values():
            for stamp in (window['start'],window['end']):
                for key in stamp:stamp[key]+=300000
            window['observedAt']=[v+300 for v in window['observedAt']]
        return {'selected':[A],'round':point,'elapsedSeconds':.25}
    def refuse(self,rounds=None,tail=None,code='TAIL'):
        with self.assertRaisesRegex(p.Refused,code):idle.assess(rounds or self.rounds(),[A,B],tail=tail)
    def test_positive_credit_is_after_window_not_measured_time(self):
        rounds=self.rounds();tail=self.point(rounds)
        value=idle.assess(rounds,[A,B],tail=tail)
        self.assertEqual(value['completedTimeDelta'],0);self.assertFalse(value['timeWitness'])
        self.assertEqual(value['completionTail']['completedTimeDelta'],1);self.assertEqual(value['classifications']['TIME_COMPLETED_AFTER_WINDOW'],1)
        self.assertEqual(idle.verify(idle.pack({**value,'rounds':rounds,'tailRound':tail}),2,['evaluator']),value)
        self.refuse(rounds,code='TAIL_REQUIRED') # original observations alone remain unqualified
    def test_mask_or_legacy_never_substitutes_for_release_credit(self):
        for key,value,code in [('completedTimeCycles',0,'COMPLETION'),('legacyCycles',3,'COMPLETION'),('completedAcquisitions',2,'NEW_DEMAND'),('failedCompletions',1,'ERROR'),('generation',2,'RESET'),('ready',False,'ERROR'),('code','unavailable','ERROR')]:
            tail=self.point();tail['round']['owners'][A][key]=value;self.refuse(tail=tail,code=code)
        for flag in idle.FLAGS:
            tail=self.point();tail['round']['owners'][A]['jobs'][flag]=True;self.refuse(tail=tail,code='JOB_PENDING')
    def test_only_final_exact_running_with_prior_opportunity(self):
        for flag in idle.FLAGS:
            if flag=='running':continue
            rounds=self.rounds();rounds[-1]['owners'][A]['jobs'][flag]=True;self.refuse(rounds,code='JOB_PENDING')
        for i in (0,1):
            rounds=self.rounds();rounds[i]['owners'][A]['jobs']['running']=True;self.refuse(rounds,code='JOB_PENDING')
        rounds=self.rounds()
        for i in (0,1):rounds[i]['owners'][A].update(dueAt=None,dueReason=None)
        self.refuse(rounds,code='OPPORTUNITY')
        rounds=self.rounds();rounds[-1]['owners'][A]['legacyCycles']=3;self.refuse(rounds,code='BODY')
        rounds=self.rounds();rounds[-1]['owners'][A].update(dueAt=220050,dueReason='new')
        self.refuse(rounds,code='OPPORTUNITY') # final-only/new pending demand cannot hide behind old due
    def test_tail_clock_coverage_budget_deadline_and_erasure(self):
        for change,code in [
            (lambda t:t.update(selected=[B]),'COVERAGE'),
            (lambda t:t.update(elapsedSeconds=5.001),'DEADLINE'),
            (lambda t:t['round']['instances']['evaluator'].update(runtimeId=S),'RESET'),
            (lambda t:t['round']['owners'].pop(A),'COVERAGE'),
            (lambda t:t['round']['allRows']['evaluator'][A].pop('dueAt'),'DUE_CONTRACT'),
            (lambda t:t['round']['owners'][A]['jobs'].pop('running'),'IDLE_JOBS'),
            (lambda t:t['round'].update(queries=2),'QUERY_BOUND'),
            (lambda t:t['round'].update(bytes=p.POLICY['maxBytesPerPhase']),'BUDGET'),
            (lambda t:t['round']['readWindows']['evaluator']['end'].update(wallUs=999999999999),'CLOCK')]:
            tail=self.point();change(tail);self.refuse(tail=tail,code=code)
        quiet=idle_fixtures.Idle().rounds();self.refuse(quiet,self.point(),code='TAIL_UNEXPECTED')
    def test_selected_foreign_rows_preserve_same_owner_and_no_work(self):
        rounds=self.rounds()
        for raw in rounds:
            raw['instances']['evaluator-2']={'runtimeId':S,'ordinal':1};raw['queries']=2
            raw['allRows']['evaluator-2']=copy.deepcopy(raw['allRows']['evaluator'])
            for row in raw['allRows']['evaluator-2'].values():row.update(service='evaluator-2',runtimeId=S,admitted=False,ready=False,completedAcquisitions=0,completedTimeCycles=0,legacyCycles=0,lastCompletedAgeMs=None,dueAt=None,dueReason=None,jobs=dict.fromkeys(idle.FLAGS,False))
            raw['readWindows']['evaluator-2']=copy.deepcopy(raw['readWindows']['evaluator'])
        tail=self.point(rounds);value=idle.assess(rounds,[A,B],tail=tail)
        self.assertEqual(value['completionTail']['queries'],2)
        self.assertEqual(idle.verify(idle.pack({**value,'rounds':rounds,'tailRound':tail}),2,['evaluator','evaluator-2']),value)
        for field,value in [('admitted',True),('generation',2),('completedTimeCycles',1),('legacyCycles',1),('ready',True)]:
            broken=copy.deepcopy(tail);broken['round']['allRows']['evaluator-2'][A][field]=value;self.refuse(rounds,broken,code='RESET|FOREIGN')
        broken=copy.deepcopy(tail);broken['round']['allRows']['evaluator-2'][A]['jobs']['running']=True;self.refuse(rounds,broken,code='JOB_PENDING')
    def test_missing_completion_guard_ablates_red_and_restores(self):
        from pathlib import Path
        source=Path(idle.__file__).read_text();needle="b['completedTimeCycles']==a['completedTimeCycles']+1 and b['legacyCycles']==a['legacyCycles']"
        self.assertIn(needle,source);ns={'__name__':'owned_tail_mutant'};exec(source.replace(needle,'True'),ns)
        tail=self.point();tail['round']['owners'][A]['completedTimeCycles']=0
        self.refuse(tail=tail,code='COMPLETION');self.assertEqual(ns['assess'](self.rounds(),[A,B],tail=tail)['verdict'],'PASS');self.refuse(tail=tail,code='COMPLETION')
    def test_observer_waits_for_metric_boundary_uses_one_global_budget(self):
        values=[];seen=[];observer=idle.Observer(['evaluator'],[A,B],None,120,'idle',values.append,tail_fetch=lambda *args:None)
        observer.rounds=self.rounds();observer.finish();self.assertEqual(values[-1]['code'],'M7_EVALUATOR_IDLE_FINAL_COMPLETION_PENDING');self.assertFalse(seen)
        tail=self.point()
        def point(services,ids,fetch):
            self.assertEqual(ids,[A]);self.assertEqual(services,['evaluator'])
            # This recording fetch exercises the actual shared deadline closure.
            with patch.object(observer,'tail_fetch',side_effect=lambda *args:seen.append(args)or b'owned'):
                fetch('evaluator',[A],999,999)
            __import__('time').sleep(.005)
            tail['round']['wallSeconds']=0
            for v in tail['round']['readWindows'].values():
                v['end']={k:n+1000 for k,n in v['start'].items()};v['observedAt']=[int(v['start']['wallUs']/1000)]
            return tail['round']
        with patch.object(idle,'round_view',side_effect=point):observer.complete_after_cost_window()
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][2],1);self.assertLessEqual(seen[0][-1],5);self.assertGreater(seen[0][-1],0)
        self.assertEqual(observer.result['completedTimeDelta'],0);self.assertEqual(observer.result['completionTail']['completedTimeDelta'],1)
    def test_one_global_deadline_is_shared_by_all_fixed_instances(self):
        for expired in (False,True):
            rounds=self.rounds()
            for raw in rounds:
                raw['instances']['evaluator-2']={'runtimeId':S,'ordinal':1};raw['queries']=2
                rows=copy.deepcopy(raw['allRows']['evaluator'])
                for row in rows.values():row.update(service='evaluator-2',runtimeId=S,admitted=False,ready=False,completedAcquisitions=0,completedTimeCycles=0,legacyCycles=0,lastCompletedAgeMs=None,dueAt=None,dueReason=None,jobs=dict.fromkeys(idle.FLAGS,False))
                raw['allRows']['evaluator-2']=rows;raw['readWindows']['evaluator-2']=copy.deepcopy(raw['readWindows']['evaluator'])
            point=self.point(rounds);clock=[0.];timeouts=[];values=[]
            def fetch(service,selected,queries,budget,timeout):
                timeouts.append(timeout);clock[0]+=4 if len(timeouts)==1 else(2 if expired else .5);return b'owned'
            observer=idle.Observer(['evaluator','evaluator-2'],[A,B],None,120,'idle',values.append,tail_fetch=fetch);observer.rounds=rounds;observer.finish()
            def observe(services,selected,read):
                self.assertEqual(selected,[A])
                for service in services:read(service,selected,99,99)
                return point['round']
            with patch.object(idle.time,'monotonic',side_effect=lambda:clock[0]),patch.object(idle,'round_view',side_effect=observe):
                if expired:
                    with self.assertRaisesRegex(p.Refused,'TAIL_DEADLINE'):observer.complete_after_cost_window()
                    self.assertEqual(values[-1]['verdict'],'UNMEASURED');self.assertIsNotNone(values[-1]['tailRound'])
                else:observer.complete_after_cost_window()
            self.assertEqual(timeouts,[5,1],'second RPC gets global remaining time, not a reset5s')
    def test_more_than_one_selector_page_refuses_before_point_fetch(self):
        rounds=self.rounds();ids=['%08x-1111-4111-8111-%012x'%(i,i)for i in range(1,130)]
        for raw in rounds:
            rows={tenant:copy.deepcopy(raw['owners'][A])for tenant in ids};raw['owners']=rows;raw['allRows']={'evaluator':rows};raw['queries']=2
        with self.assertRaisesRegex(p.Refused,'OWNER_BOUND'):idle.final_obligations(rounds,ids)

    def test_policy_and_artifact_old_versions_refuse(self):
        rounds=self.rounds();tail=self.point();v=idle.pack({**idle.assess(rounds,[A,B],tail=tail),'rounds':rounds,'tailRound':tail})
        for field,value in [('kind','evaluator-idle-safety-v1'),('policy',{**idle.POLICY,'moduleVersion':3})]:
            old=copy.deepcopy(v);old[field]=value
            with self.assertRaisesRegex(p.Refused,'IDLE_VERSION'):idle.verify(old,2,['evaluator'])

if __name__=='__main__':unittest.main()
