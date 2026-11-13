import copy,json,sys,tempfile,unittest
from pathlib import Path
import gates as G
import clinical as D
IDS=['00000000-0000-4000-8000-'+format(i,'012x')for i in range(16)]
def count_fixture():
    source={'coreCommit':'a'*40,'deployCommit':'b'*40};custody={'source':source,'imageId':'sha256:'+'c'*64,'project':'synthetic','workingDirectory':'/synthetic'}
    expected={'source':source,'custody':custody,'planSha256':'d'*64};selector=G.selector(IDS,'m7-native-'+'e'*16)
    ledgers={field:{'version':2,'kind':'m7-discovery-probe-accounting','runId':selector['runId'],'roster':IDS[:],'admissionsClosed':True,'attempts':16,'byTenant':{id:{'attempts':1,'accepted':1,'uncertain':0,'refused':0,'pending':0}for id in IDS}}for field in G.FIELDS}
    observed={'kind':'controlled-native-stored-counts','source':source,'expected':custody,'planSha256':expected['planSha256'],'selector':selector,'selectorSha256':G.canonical_hash(selector),'foreign':dict.fromkeys(G.FIELDS,0),'counts':[{'tenant':id,'entriesTotal':3,**dict.fromkeys(G.FIELDS,1)}for id in IDS]}
    return expected,selector,observed,ledgers
class Gates(unittest.TestCase):
    def test_counts_actual_contract_positive_and_foreign_misplacement_refusal(self):
        f=count_fixture();self.assertEqual(G.counts(*f)['result'],'PASS')
        foreign=copy.deepcopy(f);foreign[2]['foreign']['entries']=1
        with self.assertRaisesRegex(G.Refused,'FOREIGN_MARKED_WRITES'):G.counts(*foreign)
        misplaced=copy.deepcopy(f);misplaced[2]['counts'][0]['entries']=0;misplaced[2]['counts'][1]['entries']=2
        with self.assertRaisesRegex(G.Refused,'PER_TENANT_STORED_MISMATCH'):G.counts(*misplaced)
    def test_missing_rows_closed_ledger_and_uncertain_never_pass(self):
        for change,code in [(lambda f:f[2]['counts'].pop(),'COUNT_ROSTER'),(lambda f:f[3]['probe'].update(admissionsClosed=False),'LEDGER_IDENTITY'),(lambda f:f[3]['entries']['byTenant'][IDS[0]].update(accepted=0,pending=1),'HTTP_OUTCOME_UNMEASURED'),(lambda f:f[3]['entries'].update(attempts=15),'LEDGER_CONSERVATION')]:
            f=count_fixture();change(f)
            with self.subTest(code=code),self.assertRaisesRegex(G.Refused,code):G.counts(*f)
    def test_incomplete_roster_refuses_before_count_effect(self):
        from types import SimpleNamespace
        calls=[];host=SimpleNamespace(command=lambda *a,**k:calls.append(a))
        ports=D.Ports(host,{'ids':IDS,'runId':'m7-native-'+'e'*16})
        with self.assertRaisesRegex(G.Refused,'INCOMPLETE_SAME_MARKER_ROSTER'):ports.counts(G.selector(IDS,'m7-native-'+'f'*16),{})
        self.assertEqual(calls,[])
        with self.assertRaisesRegex(G.Refused,'COMPLETE_SIXTEEN'):G.selector(IDS[:8],'m7-native-'+'e'*16)
    def test_healthy_b_requires_causal_outage_and_independent_unchanged_identity(self):
        before={'apiCid':'api2','apiIncarnation':'api2-generation','evaluatorRuntimeId':'runtime2','evaluatorGeneration':1,'realtimeCid':'rt2','realtimeIncarnation':'rt2-generation','socketId':'socket2','completedTimeCycles':1}
        during={**before,'readStatus':200,'writeStatus':201,'ownFrameAfterWrite':True,'foreignFrames':0,'completedTimeCycles':2,'failedCompletions':0}
        v={'apiA':'api','apiB':'api-2','tenantA':IDS[0],'tenantB':IDS[1],'ownerA':'eval1','ownerB':'eval2','before':before,'during':during,'after':copy.deepcopy(during),'stopAckBeforeOutageCommand':True,'outageReplyBeforeStart':True}
        self.assertEqual(G.healthy_b(v)['result'],'PASS')
        for mutate,code in [(lambda x:x['during'].update(apiCid='api1'),'HEALTHY_B_REBOUND'),(lambda x:x.update(stopAckBeforeOutageCommand=False),'CAUSAL_BRACKETS'),(lambda x:x['during'].update(completedTimeCycles=1),'HEALTHY_B_TIME'),(lambda x:x.update(ownerB='eval1'),'HEALTHY_B_OWNER')]:
            q=copy.deepcopy(v);mutate(q)
            with self.subTest(code=code),self.assertRaisesRegex(G.Refused,code):G.healthy_b(q)
    def test_restart_old_cid_or_birth_is_not_recovery(self):
        before={'api':{'cid':'old','startedAt':'old','source':{},'imageId':'same'}};after={'api':{'cid':'new','startedAt':'new','source':{},'imageId':'same'}}
        self.assertEqual(G.restarted(before,after,['api'])['result'],'PASS')
        with self.assertRaisesRegex(G.Refused,'OLD_OR_FOREIGN_RESTART'):G.restarted(before,before,['api'])
    def test_final_zero_without_high_water_is_not_peak_proof(self):
        limits={'activeLimit':1,'pendingLimit':9};ack={'cleanShutdown':True,'unconfirmedCleanup':False,'cold':{'closed':True,'activeLimit':1,'pendingLimit':9,'queued':0,'delaying':0,'running':0}}
        with self.assertRaisesRegex(G.Refused,'NO_INSTRUMENT'):G.cold_ack(ack,limits)
        fields=('peakActive','peakQueued','accepted','started','completed','failed','duplicates','deferred','overloaded','schedulerRefused','cancelled','closeCancelled','closedRefused','invalidRefused')
        observed={'version':1,**dict.fromkeys(fields,0)};observed.update(peakActive=1,peakQueued=3,accepted=16,started=16,completed=16);ack['cold']['observed']=observed
        self.assertEqual(G.cold_ack(ack,limits)['result'],'PASS');observed['peakActive']=0
        with self.assertRaisesRegex(G.Refused,'COLD_BOUND'):G.cold_ack(ack,limits)
        observed['peakActive']=2
        with self.assertRaisesRegex(G.Refused,'COLD_BOUND'):G.cold_ack(ack,limits)
    def test_isolation_requires_explicit_refusal_and_positive_own_frame(self):
        v={'tenantA':IDS[0],'tenantB':IDS[1],'crossAuthorizationRefused':True,'socketConnectedBeforeRefusal':True,'socketExplicitRefusal':True,'foreignFrames':0,'positiveOwnFrame':True}
        self.assertEqual(G.isolation(v)['result'],'PASS')
        for k in ('socketExplicitRefusal','positiveOwnFrame'):
            with self.assertRaisesRegex(G.Refused,'ISOLATION_SOCKET'):G.isolation({**v,k:False})
    def test_cached_clinical_is_observation_not_fresh_authority(self):
        rows=[{'tenant':id,'admitted':True,'outputRevision':1,'inputCheckpoint':289,'evaluation':{'ageMs':50,'alert':None},'progress':{'generation':1,'completedAcquisitions':1,'completedTimeCycles':2,'failedCompletions':0}}for id in IDS]
        cache=[{'tenant':id,'status':'eligible-model','generation':1,'outputRevision':1,'inputCheckpoint':289,'lastCompletedAgeMs':50,'retainedModelAt':1000,'bgNow':{'meanPresent':True,'meanFinite':True,'mills':900}}for id in IDS]
        view={'kind':'evaluator','tenants':rows,'diagnostics':{'clinicalResults':{'authority':'cached-result-only','tenants':cache}}}
        self.assertEqual(G.cached_clinical(view,IDS)['controlAuthority'],'NONE')
        rows[0]['progress']['completedTimeCycles']=3
        self.assertEqual(G.cached_clinical(view,IDS)['result'],'PASS','identical TIME content may retain old model timestamp')
        cache[0]['bgNow']['meanFinite']=False
        with self.assertRaisesRegex(G.Refused,'CACHED_BG_NOW_UNAVAILABLE'):G.cached_clinical(view,IDS)
        cache[0]['bgNow']['meanFinite']=True;rows[0]['evaluation']['ageMs']=60001
        with self.assertRaisesRegex(G.Refused,'EVALUATION_CONFIRMATION_AGE_OR_ALERT'):G.cached_clinical(view,IDS)
    def test_feed_delivery_requires_same_runtime_and_positive_downstream_work(self):
        health={'live':True,'connected':True,'degraded':False,'refusal':None,'recoveryRemaining':0,'heartbeatAgeMs':5,**dict.fromkeys(('pages','checks','hints','refused','reconnects','sweeps','rotated'),0)}
        before={service:{'runtimeId':service+'-runtime','configured':{'ordinal':index},'diagnostics':{'changeFeed':{'status':'observed','health':copy.deepcopy(health)}}}for index,service in enumerate(('ev1','ev2'))}
        after=copy.deepcopy(before)
        for row in after.values():row['diagnostics']['changeFeed']['health'].update(checks=2,hints=1)
        self.assertEqual(G.feed_delivery(before,after,5000)['result'],'PASS');after['ev1']['runtimeId']='replacement'
        with self.assertRaisesRegex(G.Refused,'FEED_RUNTIME_CHANGED'):G.feed_delivery(before,after,5000)
    def test_late_socket_budget_refusal_cannot_pass_final_accounting(self):
        for closed in ({'socketBudgetRefused':True,'socketBytes':268435457},{'socketBudgetRefused':False},{}):
            with self.assertRaisesRegex(G.Refused,'SOCKET_INPUT_BUDGET_UNCONFIRMED'):G.raw_http_ledgers(closed,'/must-not-read-any-receipt')
    def test_runtime_source_guard_precedes_any_host_construction(self):
        from unittest.mock import patch
        import runtime
        plan={'runtimeReady':True,'root':'/synthetic','topology':{},'hostDependencies':{}}
        with patch.object(D,'prepare',return_value=plan),patch.object(D.DEP,'capture',return_value={}),patch.object(runtime,'Host',side_effect=AssertionError('HOST_MUST_NOT_BE_CONSTRUCTED'))as host:
            with self.assertRaisesRegex(G.Refused,'FINAL_SOURCE_JOIN_REQUIRED_BEFORE_EFFECTS'):runtime.execute(plan,'/unused')
            host.assert_not_called()
    def test_owned_producer_cancellation_retains_and_drains_group(self):
        import os,threading
        cancel=threading.Event();cancel.set()
        with tempfile.TemporaryDirectory()as directory:
            result=D.O.run([sys.executable,'-c','import time;time.sleep(30)'],{'PATH':os.environ['PATH']},Path(directory)/'child',.2,65536,cancel_event=cancel)
            self.assertEqual(result['failure'],'COMMAND_CANCELLED');self.assertTrue(result['groupDrained']);self.assertEqual(result['operationOutcome'],'UNKNOWN')
    def test_model_keeps_healthy_b_inside_only_api_outage(self):
        plan={'slots':['admin','api','api-2','realtime','realtime-2','evaluator','evaluator-2','tenant-admin','ui','socket-edge','feed-reader'],'cohort':[{'service':s}for s in ('api','api-2','realtime','realtime-2','evaluator','evaluator-2','tenant-admin')],'steps':list(D.STEPS),'source':{}}
        with tempfile.TemporaryDirectory()as p:
            result=D.dry_run(plan,Path(p)/'run');self.assertEqual(result['runtime'],'NOT_RUN');self.assertEqual(result['nativeAcceptance'],'UNMEASURED')
        r=D.Recording(plan);r.event('start-all-eleven')
        with self.assertRaisesRegex(G.Refused,'HEALTHY_B_NOT_DURING_OUTAGE'):r.event('healthy-B-during-outage')
if __name__=='__main__':unittest.main()
