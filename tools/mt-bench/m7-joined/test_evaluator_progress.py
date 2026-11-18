import copy
import json
from pathlib import Path
import sys
import os
import subprocess
import evaluator_recovery as recovery
import unittest
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import evaluator_progress as p

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
R='33333333-3333-4333-8333-333333333333'
S='44444444-4444-4444-8444-444444444444'

class ReadinessClock:
    now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Progress(unittest.TestCase):
    def refused_frame(self):
        value=self.frame(ids=[A]);row=value['view']['tenants'][0]
        row.update(ready=False,code='SYNTHETIC_READY_FALSE')
        row['evaluation']['alert']='synthetic-alert'
        row['progress'].update(generation=17,completedAcquisitions=5,lastCompletedAgeMs=123)
        row['clinicalOutput']={'excluded':'not refusal evidence'}
        return value
    def refused(self,frame=None,verdict='FAIL'):
        raw=json.dumps(frame or self.refused_frame()).encode()
        with self.assertRaises(p.Refused) as caught:p.round_view(['evaluator'],[A],lambda *_:raw,warming=True)
        self.assertEqual(caught.exception.verdict,verdict)
        return caught.exception
    def assert_failed_row_evidence(self):
        error=self.refused();e=error.diagnostic.get('failedRow',{})
        self.assertEqual(e.get('tenant'),A)
        self.assertEqual((e['service'],e['runtimeId'],e['ready'],e['code'],e['alert']),('evaluator',R,False,'SYNTHETIC_READY_FALSE','synthetic-alert'))
        self.assertEqual(e['progress']['generation'],17)
        self.assertEqual(e['progress']['completedAcquisitions'],5)
        self.assertEqual(e['dueReason'],'pump-clock-warn')
        self.assertNotIn('clinicalOutput',e)
        self.assertEqual(error.diagnostic['predicate'],'OWNER_READY_REQUIRED')
        return error
    def test_readiness_refusal_persists_actual_bounded_failed_row(self):
        import adapter as a
        expected=self.assert_failed_row_evidence().diagnostic
        with tempfile.TemporaryDirectory() as name:
            d=Path(name);(d/'tenants.private.json').write_text(json.dumps([{'id':A}]))
            with patch.object(a,'progress_services',return_value=['evaluator']),patch.object(a,'progress_fetch',return_value=json.dumps(self.refused_frame())):
                with self.assertRaises(p.Refused):a.readiness(d,{})
            saved=json.loads((d/'runtime-readiness.json').read_text())
            self.assertEqual(saved['verdict'],'FAIL')
            self.assertEqual(saved['observations'][0]['diagnostic'],expected)
    def test_failed_row_evidence_removal_ablation_red_and_restore_green(self):
        self.assert_failed_row_evidence()
        with patch.object(p,'_refusal_row',return_value={}):
            with self.assertRaisesRegex(AssertionError,'None !='):
                self.assert_failed_row_evidence()
        self.assert_failed_row_evidence()
    def test_actual_readiness_discovery_keeps_unknown_history_and_strict_stays_red(self):
        import adapter as a
        frame=self.frame(ids=[A]);frame['view']['tenants'][0]['progress']['failedCompletions']=2
        for discovery in (False,True):
            with tempfile.TemporaryDirectory() as name:
                d=Path(name);(d/'tenants.private.json').write_text(json.dumps([{'id':A}]))
                with patch.object(a,'progress_services',return_value=['evaluator']),patch.object(a,'progress_fetch',return_value=json.dumps(frame)):
                    if discovery:a.readiness(d,{'runPurpose':'discovery'})
                    else:
                        with self.assertRaisesRegex(p.Refused,'PROGRESS_ERROR'):a.readiness(d,{})
                saved=json.loads((d/'runtime-readiness.json').read_text())
                self.assertEqual(saved['verdict'],'PASS' if discovery else 'FAIL')
                if discovery:self.assertEqual(saved['observations'][0]['causeAttribution'],'UNMEASURED')

    def test_selected_readiness_window_reaches_late_strict_confirmation(self):
        import adapter as a
        ready=self.frame(ids=[A])
        warming=copy.deepcopy(ready)
        warming['view']['tenants'][0].update(ready=False,code='EVALUATOR_STARTING')
        budget={'maxQueriesPerPhase':9,'maxBytesPerPhase':12000}
        for selection,code in (({},'M7_RUNTIME_NOT_READY'),({'evaluatorReadySeconds':1500},None)):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as name:
                clock=ReadinessClock()
                d=Path(name);a.write(d/'tenants.private.json',[{'id':A}])
                cadence={'startupWindows':selection,'evaluatorProgressBudget':budget}
                def fetch(*args, timeout):
                    return json.dumps(warming if clock.now<1215 else ready)
                with patch.object(a,'progress_services',return_value=['evaluator']), patch.object(a,'progress_fetch',side_effect=fetch):
                    if code:
                        with self.assertRaisesRegex(p.Refused,code):
                            a.readiness(d,{'runPurpose':'discovery','cadence':cadence},clock=clock)
                    else:
                        result=a.readiness(d,{'runPurpose':'discovery','cadence':cadence},clock=clock)
                saved=a.document(d/'runtime-readiness.json')
                if code:
                    self.assertEqual((clock.now,saved['code']),(1200,'M7_RUNTIME_NOT_READY'))
                else:
                    self.assertEqual((clock.now,result['verdict']),(1215.25,'PASS'))
                    self.assertNotIn('code',saved)
                    self.assertEqual(saved['observations'][0]['code'],'M7_EVALUATOR_PROGRESS_ERROR')
                    self.assertEqual(saved['capture']['limits'],{'attempts':100,'queries':200,'bytes':800000})
                    used=saved['capture']['used']
                    self.assertEqual((used['attempts'],used['queries']),(82,83))
                    self.assertGreater(used['bytes'],0)
                    self.assertEqual(saved['policy']['maxBytesPerPhase'],budget['maxBytesPerPhase'])

    def test_readiness_reports_capture_exhaustion_and_preserves_a_strict_refusal(self):
        import adapter as a
        for confirmation,code,verdict in ((self.frame(ids=[A]),'M7_EVALUATOR_PROGRESS_READINESS_BUDGET','UNMEASURED'),
                                          (self.refused_frame(),'M7_EVALUATOR_PROGRESS_ERROR','FAIL')):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as name:
                clock=ReadinessClock()
                d=Path(name);a.write(d/'tenants.private.json',[{'id':A}])
                frames=[json.dumps(value) for value in (self.frame(ids=[A]),confirmation)]
                with patch.dict(p.POLICY,{'readinessMaxQueries':1}), patch.object(a,'progress_services',return_value=['evaluator']), patch.object(a,'progress_fetch',side_effect=frames):
                    with self.assertRaisesRegex(p.Refused,code) as caught:
                        a.readiness(d,{'runPurpose':'discovery'},clock=clock)
                saved=a.document(d/'runtime-readiness.json')
                self.assertEqual((clock.now,caught.exception.verdict,saved['code'],saved['capture']['used']['queries']),
                                 (.25,verdict,code,2))

    def test_refusal_evidence_bounds_malformed_fields_without_losing_refusal(self):
        frame=self.refused_frame();row=frame['view']['tenants'][0]
        row['code']='C'*100000;row['evaluation']['alert']='\u2603'*100000
        row['progress']['generation']=10**1000
        error=self.refused(frame,verdict='UNMEASURED');e=error.diagnostic['failedRow']
        self.assertLessEqual(len(json.dumps(e).encode()),p.REFUSAL_ROW_MAX_BYTES)
        self.assertTrue(e['code']['truncated']);self.assertEqual(e['code']['length'],100000)
        self.assertTrue(e['alert']['truncated']);self.assertEqual(e['progress']['generation'],{'type':'int'})
        row['evaluation']['alert']={'malformed':['x'*100000]}
        e=self.refused(frame,verdict='UNMEASURED').diagnostic['failedRow']
        self.assertEqual(e['alert'],{'type':'dict'})
        self.assertLessEqual(len(json.dumps(e).encode()),p.REFUSAL_ROW_MAX_BYTES)

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
        self.assertEqual(p.assess(rounds,[A,B],'idle')['verdict'],'PASS')
        self.assertEqual(p.assess(rounds,[A,B],'load')['verdict'],'PASS')
    def test_hidden_recovered_failure_and_runtime_generation_reset_fail(self):
        for field,value in [('failedCompletions',1),('completedAcquisitions',0)]:
            rounds=[self.round(i) for i in range(3)];rounds[-1]['owners'][A][field]=value
            with self.assertRaises(p.Refused) as caught:p.assess(rounds,[A,B],'load')
            self.assertEqual(caught.exception.verdict,'FAIL')
        rounds=[self.round(i) for i in range(3)];rounds[-1]['instances']['evaluator']['runtimeId']=S
        with self.assertRaisesRegex(p.Refused,'RESET'):p.assess(rounds,[A,B],'load')
    def test_discovery_historical_uncredited_attempts_are_unknown_not_clinical_failures(self):
        rounds=[self.round(i) for i in range(3)]
        for index,value in enumerate(rounds):
            value['owners'][A]['failedCompletions']=3+index
        admission=p.stable_discovery_baseline(rounds[0],rounds[-1],[A,B])
        self.assertEqual(admission['baselineUncreditedAttempts'],3)
        self.assertEqual(admission['uncreditedAttemptDelta'],2)
        self.assertEqual(admission['causeAttribution'],'UNMEASURED')
        with self.assertRaisesRegex(p.Refused,'HIDDEN_FAILURE'):p.assess(rounds,[A,B],'load')
        broken=copy.deepcopy(rounds);broken[-1]['owners'][A]['failedCompletions']=0
        with self.assertRaisesRegex(p.Refused,'RESET'):p.stable_discovery_baseline(broken[0],broken[-1],[A,B])
        broken=copy.deepcopy(rounds);broken[-1]['owners'][A]['code']='EVALUATOR_WINDOW_REFUSED'
        with self.assertRaisesRegex(p.Refused,'PROGRESS_ERROR'):p.stable_discovery_baseline(broken[0],broken[-1],[A,B])

    def test_default_discovery_selection_control_and_restore(self):
        import adapter as a
        from types import SimpleNamespace
        def criterion(select):
            m={'runPurpose':'discovery','profile':'pgstream-sample','completionContract':'evaluator-work-v2'}
            select(SimpleNamespace(evaluator_opportunities=None),m)
            self.assertEqual(m.get('evaluatorOpportunities'),'received-input-v1')
        criterion(a.select_opportunities)
        with self.assertRaises(AssertionError):criterion(lambda args,m:None)
        criterion(a.select_opportunities)

    def test_discovery_unavailable_preserves_actual_ready_and_job_state(self):
        for changed,reason in [({'running':True},'BUSY'),({'booting':True},'BOOTING'),({},'COLD_OR_UNOBSERVED')]:
            frame=self.frame(ids=[A]);raw=frame['view']['tenants'][0];raw.update(ready=False,jobs={**dict.fromkeys(p.JOB_FLAGS,False),**changed})
            fetch=lambda *_:json.dumps(frame).encode()
            point=p.round_view(['evaluator'],[A],fetch,allow_unavailable=True)
            self.assertFalse(point['owners'][A]['ready'])
            result=p.availability([point],[A]);self.assertEqual(result['verdict'],'UNMEASURED');self.assertEqual(result['classifications'][reason],1)
            packed=p.pack({'rounds':[point]})
            decoded,_=p.decode_rounds(packed,1,['evaluator'],allow_unavailable=True)
            self.assertEqual(decoded[0]['owners'][A]['jobState'],raw['jobs'])
            with self.assertRaisesRegex(p.Refused,'PROGRESS_ERROR'):p.decode_rounds(packed,1,['evaluator'])
            with self.assertRaisesRegex(p.Refused,'PROGRESS_ERROR'):p.round_view(['evaluator'],[A],fetch)
            for key,value in [('code','EVALUATOR_WINDOW_REFUSED'),('evaluation',{'alert':'CURRENT_ERROR'})]:
                bad=copy.deepcopy(frame);bad['view']['tenants'][0][key]=value
                with self.assertRaisesRegex(p.Refused,'PROGRESS_ERROR'):p.round_view(['evaluator'],[A],lambda *_:json.dumps(bad),allow_unavailable=True)
            packed['rounds'][0]['rows'][0][p.COLUMNS.index('jobState')]=None
            with self.assertRaisesRegex(p.Refused,'PROGRESS_CONTRACT'):p.decode_rounds(packed,1,['evaluator'],allow_unavailable=True)

    def test_actual_readiness_discovery_unavailability_is_unmeasured(self):
        import adapter as a
        frame=self.frame(ids=[A]);frame['view']['tenants'][0].update(ready=False,jobs=dict.fromkeys(p.JOB_FLAGS,False))
        with tempfile.TemporaryDirectory() as name:
            d=Path(name);(d/'tenants.private.json').write_text(json.dumps([{'id':A}]))
            with patch.object(a,'progress_services',return_value=['evaluator']),patch.object(a,'progress_fetch',return_value=json.dumps(frame)):
                result=a.readiness(d,{'runPurpose':'discovery'})
            self.assertEqual(result['verdict'],'UNMEASURED')
            saved=json.loads((d/'readiness-stable-baseline.private.json').read_text())
            self.assertFalse(saved['rounds'][0]['rows'][0][p.COLUMNS.index('ready')])

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
            p.round_view([f'evaluator-{i}' for i in range(1,10)],[A],lambda *_:b'')

    def test_eight_static_instances_require_exact_worker_ordinals(self):
        services=['evaluator', *(f'evaluator-{i}' for i in range(2,9))]
        ids=[f'00000000-0000-4000-8000-{i:012x}' for i in range(8)]
        def fetch(service, *_):
            index=services.index(service)
            ordinal=index+int(broken and index==7)
            value=self.frame(ids,ordinal=ordinal,runtime=f'99999999-9999-4999-8999-{index:012x}')
            value.update(selfMode='static',selfCount=len(services))
            view=value['view']
            view['configured'].update(mode='static',count=len(services),rule='sha256-modulo-v1',leaseMs=None)
            view['gate']['members']=len(services)
            view['observed']=None
            for i,row in enumerate(view['tenants']):
                if i!=index: row.update(admitted=False,ready=False)
            return json.dumps(value).encode()
        broken=False
        for restored in (False, True):
            value=p.round_view(services,ids,fetch)
            self.assertEqual([value['owners'][tenant]['service'] for tenant in ids],services)
            self.assertEqual(value['queries'],8)
            if not restored:
                broken=True
                with self.assertRaisesRegex(p.Refused,'STATIC_CONFIGURATION'):p.round_view(services,ids,fetch)
                broken=False

    def test_selected_capture_budget_reaches_wide_query_and_is_required_on_retained_proof(self):
        services=['evaluator', *(f'evaluator-{i}' for i in range(2,9))]
        wide=[f'00000000-0000-4000-8000-{i:012x}' for i in range(10000)]
        native=[]
        def read(service,ids,queries,byte_budget):
            native.append((service,len(ids),queries,byte_budget))
            raise p.Refused('SYNTHETIC_CAPTURE_BOUNDARY')
        with self.assertRaisesRegex(p.Refused,'QUERY_BOUND'):p.round_view(services,wide,read)
        self.assertEqual(native,[])
        selected={'maxQueriesPerPhase':1896,'maxBytesPerPhase':128*1024*1024}
        policy=p.capture_policy(selected)
        with self.assertRaisesRegex(p.Refused,'SYNTHETIC_CAPTURE_BOUNDARY'):
            p.round_view(services,wide,read,policy=policy)
        self.assertEqual(sorted(native),[(service,10000,79,selected['maxBytesPerPhase']//24) for service in services])
        exhausted=p.capture_policy({**selected,'maxBytesPerPhase':3})
        with self.assertRaisesRegex(p.Refused,'BYTE_BOUND') as caught:
            p.round_view(['evaluator'],[A],lambda *_:json.dumps(self.frame(ids=[A])).encode(),policy=exhausted)
        self.assertEqual(caught.exception.verdict,'UNMEASURED')
        rounds=[self.round(i) for i in range(3)]
        expected=p.assess(rounds,[A,B],'load',policy=policy)
        record=p.pack({**expected,'rounds':rounds})
        self.assertEqual(p.verify(record,2,['evaluator'],'load',budget=selected),expected)
        with self.assertRaisesRegex(p.Refused,'PROOF'):p.verify(record,2,['evaluator'],'load')
        with self.assertRaisesRegex(p.Refused,'PROOF'):
            p.verify(record,2,['evaluator'],'load',budget={**selected,'maxQueriesPerPhase':1895})
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
        # The source roster grows within the same observation budgets.
        self.assertEqual({k:v for k,v in p.POLICY.items() if k not in ('version','dueState','moduleVersion','cacheGeneration','idleWitness','maxTenants','maxInstances')},{k:v for k,v in p.LEGACY_POLICY.items() if k not in ('version','moduleVersion','idleWitness','maxTenants','maxInstances')})
        self.assertEqual(p.POLICY['maxTenants'],2**32-1)
        for policy in (p.REFERENCE_POLICY,p.PREVIOUS_POLICY):
            old=p.assess(rounds,[A,B],'idle',policy=policy)
            self.assertEqual(p.verify(p.pack({**old,'rounds':rounds}),2,['evaluator'],'idle'),old)
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
        rounds[-1]['owners'][A]['generation']+=10
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
        needle="work>0 and (policy!=LEGACY_POLICY or phase!='idle' or delta>0)"
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
