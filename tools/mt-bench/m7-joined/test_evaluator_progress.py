import copy
import json
from pathlib import Path
import sys
import os
import subprocess
import evaluator_recovery as recovery
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import evaluator_progress as p

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
R='33333333-3333-4333-8333-333333333333'
S='44444444-4444-4444-8444-444444444444'
class Progress(unittest.TestCase):
    def frame(self,ids=None,ordinal=0,runtime=R,increment=0):
        ids=ids or [A,B]
        return {'selected':ids,'selfOrdinal':ordinal,'selfMode':'partitioned','view':{'kind':'evaluator','runtimeId':runtime,'configured':{'ordinal':ordinal,'mode':'partitioned'},'gate':{'eligible':True,'reason':None},'tenants':[{'tenant':tenant,'admitted':True,'ready':True,'cycles':1+increment,'dueAt':1700000008572.4285,'dueReason':'pump-clock-warn','code':None,'evaluation':{'alert':None},'progress':{'generation':i+1,'completedAcquisitions':1+increment,'completedTimeCycles':increment,'failedCompletions':0,'lastCompletedAgeMs':0}} for i,tenant in enumerate(ids)]}}
    def round(self,increment=0,transform=lambda x:x):
        return p.round_view(['evaluator'],[A,B],lambda *_:json.dumps(transform(self.frame(increment=increment))).encode()+b'\n')
    def test_successful_idle_and_load_are_distinct_and_no_true_cold_claim(self):
        rounds=[self.round(i) for i in range(3)]
        for phase in ('idle','load'):
            result=p.assess(rounds,[A,B],phase);self.assertEqual(result['verdict'],'PASS');self.assertEqual(result['tenantsWithTimeProgress'],2)
        self.assertFalse(p.POLICY['workloadCohortChanged']);self.assertFalse(p.POLICY['deadlineClaim'])
    def test_stale_worker_and_acquisition_only_idle_are_unmeasured(self):
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess([self.round()]*3,[A,B],'idle')
        rounds=[self.round(i,lambda x:dict(x)) for i in range(3)]
        for value in rounds:
            for row in value['owners'].values():row['completedTimeCycles']=0
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(rounds,[A,B],'idle')
        self.assertEqual(p.assess(rounds,[A,B],'load')['verdict'],'PASS')
    def test_hidden_recovered_failure_and_runtime_generation_reset_fail(self):
        for field,value in [('failedCompletions',1),('generation',9),('completedAcquisitions',0)]:
            rounds=[self.round(i) for i in range(3)];rounds[-1]['owners'][A][field]=value
            with self.assertRaises(p.Refused) as caught:p.assess(rounds,[A,B],'load')
            self.assertEqual(caught.exception.verdict,'FAIL')
        rounds=[self.round(i) for i in range(3)];rounds[-1]['instances']['evaluator']['runtimeId']=S
        with self.assertRaisesRegex(p.Refused,'RESET'):p.assess(rounds,[A,B],'load')
    def test_closed_window_state_and_wrong_self_coverage_fail(self):
        def broken(frame):frame['view']['tenants'][0]['code']='EVALUATOR_WINDOW_REFUSED';return frame
        with self.assertRaises(p.Refused) as caught:self.round(transform=broken)
        self.assertEqual(caught.exception.verdict,'FAIL')
        def swapped(frame):frame['selfOrdinal']=1;return frame
        with self.assertRaisesRegex(p.Refused,'INSTANCE'):self.round(transform=swapped)
        def missing(frame):frame['view']['tenants'].pop();return frame
        with self.assertRaisesRegex(p.Refused,'COVERAGE'):self.round(transform=missing)
        with self.assertRaisesRegex(p.Refused,'COVERAGE'):
            p.round_view(['a','b'],[A,B],lambda *_:json.dumps(self.frame()).encode())
    def test_missing_completion_contract_and_byte_query_budgets_refuse(self):
        def old(frame):frame['view'].pop('runtimeId');return frame
        with self.assertRaisesRegex(p.Refused,'CONTRACT'):self.round(transform=old)
        with self.assertRaisesRegex(p.Refused,'BYTE_BOUND'):
            p.round_view(['evaluator'],[A],lambda *_:b'x'*(p.POLICY['maxBytesPerPhase']//3+1))
        with self.assertRaisesRegex(p.Refused,'INSTANCE_BOUND'):
            p.round_view(['a','b','c','d','e'],[A],lambda *_:b'')
    def partitioned(self,step=0):
        def fetch(service,*_):
            ordinal=0 if service=='a' else 1;frame=self.frame(ordinal=ordinal,runtime=R if ordinal==0 else S,increment=step)
            for index,row in enumerate(frame['view']['tenants']):
                if index!=ordinal:
                    row.update(admitted=False,ready=False,code='EVALUATOR_POOL_NOT_IN_SLICE',cycles=7,dueAt=None,dueReason=None)
                    row['progress'].update(completedAcquisitions=7,completedTimeCycles=3,lastCompletedAgeMs=100)
            return json.dumps(frame).encode()
        return p.round_view(['a','b'],[A,B],fetch)
    def test_foreign_rows_retained_with_explicit_baseline_and_no_new_work(self):
        rounds=[self.partitioned(i) for i in range(3)]
        value=p.assess(rounds,[A,B],'idle');record=p.pack({**value,'rounds':rounds})
        self.assertEqual(len(record['rounds'][0]['rows']),4)
        self.assertEqual(p.verify(record,2,['a','b'],'idle'),value)
        for metric in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles'):
            broken=copy.deepcopy(rounds);broken[-1]['allRows']['a'][B][metric]+=1
            with self.assertRaisesRegex(p.Refused,'FOREIGN'):p.assess(broken,[A,B],'idle')
        broken=copy.deepcopy(record);broken['rounds'][0]['rows'].pop()
        with self.assertRaisesRegex(p.Refused,'COVERAGE'):p.verify(broken,2,['a','b'],'idle')
    def test_compact_proof_cannot_fake_success_or_hidden_recovery(self):
        rounds=[self.round(i) for i in range(3)];value=p.assess(rounds,[A,B],'load');record=p.pack({**value,'rounds':rounds})
        self.assertEqual(p.verify(record,2,['evaluator'],'load'),value)
        record['rounds'][-1]['rows'][0][p.COLUMNS.index('failedCompletions')]=1
        with self.assertRaisesRegex(p.Refused,'HIDDEN_FAILURE'):p.verify(record,2,['evaluator'],'load')

    def test_due_fields_retained_without_changing_progress_policy(self):
        rounds=[self.round(i) for i in range(3)];result=p.assess(rounds,[A,B],'idle');record=p.pack({**result,'rounds':rounds})
        self.assertEqual(record['kind'],'evaluator-progress-phase-v2')
        self.assertEqual({k:v for k,v in p.POLICY.items() if k not in ('version','dueState')},{k:v for k,v in p.LEGACY_POLICY.items() if k!='version'})
        decoded,ids=p.decode_rounds(record,2,['evaluator'])
        self.assertEqual(decoded[0]['owners'][A]['dueAt'],1700000008572.4285)
        self.assertEqual(decoded[0]['owners'][A]['dueReason'],'pump-clock-warn')
        self.assertEqual(p.verify(record,2,['evaluator'],'idle'),result)
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess([self.round()]*3,[A,B],'idle')
        for due in ({'dueAt':None,'dueReason':None},{'dueAt':1.5,'dueReason':None},{'dueAt':1.7976931348623157e308,'dueReason':'synthetic-future'}):
            self.assertEqual(p.due_fields(due),due)
        for due in ({},{'dueAt':1},{'dueAt':-1,'dueReason':None},{'dueAt':float('inf'),'dueReason':None},{'dueAt':float('nan'),'dueReason':None},{'dueAt':'1','dueReason':None},{'dueAt':False,'dueReason':None},{'dueAt':None,'dueReason':'stale-reason'},{'dueAt':1,'dueReason':'private free text'},{'dueAt':1,'dueReason':'a'*129}):
            with self.assertRaisesRegex(p.Refused,'DUE_CONTRACT'):p.due_fields(due)
        def missing(frame):frame['view']['tenants'][0].pop('dueAt');return frame
        with self.assertRaisesRegex(p.Refused,'DUE_CONTRACT'):self.round(transform=missing)
        broken=copy.deepcopy(record);broken['kind']='evaluator-progress-phase-v1'
        with self.assertRaisesRegex(p.Refused,'PROOF'):p.verify(broken,2,['evaluator'],'idle')

    def test_historical_real_captures_keep_original_policy_and_unknown_due(self):
        root=Path(__file__).resolve().parents[3]/'reports/tenancy/evaluator-trusted-scheduling-2026-11-12'
        for name in ('native-listener-195c-f0f91','native-listener-cd462-0f8749-unmeasured'):
            file=root/name/'native-observation.json';before=file.read_bytes();value=json.loads(before);record=value['proof'];services=sorted(value['containers'])
            decoded,ids=p.decode_rounds(record,2,services)
            self.assertTrue(all('dueAt' not in row and 'dueReason' not in row for rows in decoded[0]['allRows'].values() for row in rows.values()))
            if value['result']['verdict']=='PASS':self.assertEqual(p.verify(record,2,services,'idle'),value['result'])
            else:
                with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(decoded,sorted(ids),'idle',policy=p.LEGACY_POLICY)
            self.assertEqual(file.read_bytes(),before)

    def test_body_failure_preserves_partial_evidence_and_original_exception(self):
        recorded=[];original=ValueError('intentional body failure')
        observer=p.Observer(['evaluator'],[A,B],lambda *_:json.dumps(self.frame()).encode(),120,'load',recorded.append)
        with self.assertRaises(ValueError) as caught:
            with observer:raise original
        self.assertIs(caught.exception,original);self.assertEqual(recorded[0]['verdict'],'FAIL');self.assertEqual(len(recorded[0]['rounds']),1);self.assertTrue(recorded[0]['interruptedBody'])

    def test_selected_pages_exact_coverage_and_runtime_stable(self):
        ids=['00000000-0000-4000-8000-'+str(i).zfill(12) for i in range(129)]
        def fetch(*_):return b'\n'.join(json.dumps(self.frame(ids=part)).encode() for part in [ids[:128],ids[128:]])
        value=p.round_view(['evaluator'],ids,fetch);self.assertEqual(value['queries'],2);self.assertEqual(set(value['owners']),set(ids))
        def changed(*_):return json.dumps(self.frame(ids=ids[:128])).encode()+b'\n'+json.dumps(self.frame(ids=ids[128:],runtime=S)).encode()
        with self.assertRaisesRegex(p.Refused,'RESET'):p.round_view(['evaluator'],ids,changed)

class Recovery(unittest.TestCase):
    frame=Progress.frame
    round=Progress.round
    def test_recovery_requires_changed_runtime_and_fresh_success_not_cycles(self):
        baseline=self.round();rounds=[self.round(i) for i in (1,2)]
        for value in rounds:
            value['instances']['evaluator']['runtimeId']=S
            for row in value['owners'].values():row['runtimeId']=S
        self.assertEqual(recovery.assess(baseline,rounds,[A,B])['missing'],0)
        broken=copy.deepcopy(rounds);broken[0]['instances']=baseline['instances']
        with self.assertRaisesRegex(p.Refused,'OLD_RUNTIME'):recovery.assess(baseline,broken,[A,B])
        for value in rounds:
            for row in value['owners'].values():row['completedAcquisitions']=0
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):recovery.assess(baseline,rounds,[A,B])

class OracleAblation(unittest.TestCase):
    def test_stopped_worker_refusal_becomes_false_pass_when_completion_guard_removed(self):
        fixture=Progress();rounds=[fixture.round() for _ in range(3)]
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(rounds,[A,B],'idle')
        needle="work>0 and (phase!='idle' or delta>0)"
        source=Path(p.__file__).read_text();self.assertEqual(source.count(needle),1)
        namespace={'__name__':'owned_scratch_progress_mutant'};exec(compile(source.replace(needle,'True'),'owned_scratch_progress_mutant','exec'),namespace)
        self.assertEqual(namespace['assess'](rounds,[A,B],'idle')['verdict'],'PASS','control must expose a false pass')
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(rounds,[A,B],'idle')

class ActualComponent(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('M7_PROGRESS_CORE'),'owned product source fixture not selected')
    def test_actual_window_time_completion_and_stopped_scheduler_noninterference(self):
        fixture=Path(__file__).with_name('evaluator-progress-fixture.cjs')
        for stopped in (False,True):
            env={**os.environ,'M7_PROGRESS_STOPPED':'1' if stopped else '0'}
            result=subprocess.run(['node',str(fixture)],env=env,capture_output=True,check=True,timeout=20)
            rounds=[p.round_view(['evaluator'],[A],lambda *_,line=line:line) for line in result.stdout.splitlines()]
            actual=rounds[0]['owners'][A]['dueAt'];self.assertIsInstance(actual,float);self.assertNotEqual(actual,int(actual));self.assertEqual(rounds[0]['owners'][A]['dueReason'],'pump-clock-warn')
            packed=p.pack({'rounds':rounds});decoded,_=p.decode_rounds(packed,1,['evaluator']);self.assertEqual(decoded[0]['owners'][A]['dueAt'],actual)
            if stopped:
                with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(rounds,[A],'idle')
            else:self.assertEqual(p.assess(rounds,[A],'idle')['verdict'],'PASS')

if __name__=='__main__':unittest.main()
