"""Finite discovery remainder at stage and executor boundaries; no app actors."""
import tempfile,time,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import adapter as a

class DiscoveryWindow(unittest.TestCase):
    def test_original_cutoff_replaces_only_discovery_stage_defaults(self):
        m={'profile':'pgstream-sample','runPurpose':'discovery'}
        with patch.object(a.time,'time',return_value=100):
            self.assertEqual(a.discovery_seconds(m,1800),1800)
            with a.command_deadline(9000):
                self.assertEqual(a.discovery_seconds(m,1800),8900)
                self.assertEqual(a.discovery_seconds({**m,'runPurpose':'acceptance'},1800),1800)
                with a.command_deadline(10000):self.assertEqual(a.discovery_seconds(m,600),8900)
                with a.command_deadline(110):self.assertEqual(a.discovery_seconds(m,600),10)
                with patch.object(a.time,'time',return_value=8990):self.assertEqual(a.discovery_seconds(m,600),10)
                with patch.object(a.time,'time',return_value=9000):
                    with self.assertRaisesRegex(RuntimeError,'COMMAND_DEADLINE'):a.discovery_seconds(m,600)

    def test_progress_fetch_executor_retains_cutoff_without_extending_query_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);a.write(d/'tenants.private.json',[{'id':'synthetic'}])
            m={'cadence':{'loadSeconds':60}}
            with patch.object(a,'progress_services',return_value=['evaluator']),a.command_deadline(9000):
                observer=a.observe_progress(d,m,d,'load')
            def fetch(*args):return a.remaining_seconds(20)
            with patch.object(a,'progress_fetch',side_effect=fetch),patch.object(a.time,'time',return_value=8995),ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(observer.fetch,'evaluator',[],1,1).result(),5)
            with patch.object(a,'progress_fetch',side_effect=fetch),patch.object(a.time,'time',return_value=9000),ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaisesRegex(RuntimeError,'COMMAND_DEADLINE'):pool.submit(observer.fetch,'evaluator',[],1,1).result()

class StaticSliceProgress(unittest.TestCase):
    """Compose K=2: core evaluator-inspection.js refuses a selector naming a tenant outside the
    slice, which the helper reports as a failed exec (reproduced on core 1385543c6)."""
    def run_load(self,workers):
        import json
        import evaluator_progress as p
        ids=['30000002-3333-4333-8333-000000000002','11111111-1111-4111-8111-111111111111',
             '22222222-2222-4222-8222-222222222222','3000000f-3333-4333-8333-00000000000f']
        services=['evaluator','evaluator-2']
        self.assertEqual({p.bucket(t,2) for t in ids},{0,1})
        asked=[]
        def compose(d,*args,input=None,**kw):
            service=args[2];ordinal=p.service_ordinal(service)
            selected=json.loads(input.decode().split(';',1)[0].removeprefix('const M7_PROGRESS_IDS='))
            asked.append((service,tuple(selected)))
            if any(p.bucket(t,2)!=ordinal for t in selected):raise RuntimeError('M7_COMMAND_FAILED:docker')
            rows=[{'tenant':t,'admitted':True,'ready':True,'code':None,'evaluation':{'alert':None},'cycles':1,
                   'progress':{'generation':1,'completedAcquisitions':1,'completedTimeCycles':0,'failedCompletions':0,'lastCompletedAgeMs':1},
                   'jobs':dict.fromkeys(p.JOB_FLAGS,False),'dueAt':None,'dueReason':None} for t in selected]
            configured={'ordinal':ordinal,'mode':'static','count':2,'rule':'sha256-modulo-v1','leaseMs':None}
            return json.dumps({'selected':selected,'selfOrdinal':ordinal,'selfMode':'static','selfCount':2,
                               'view':{'kind':'evaluator','runtimeId':'5c35b258-f6ef-4af6-9a93-7fe985d38d7'+str(ordinal),
                                       'configured':configured,'observed':None,'gate':{'eligible':True,'reason':None,'members':2},'tenants':rows}})+'\n'
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);a.write(d/'tenants.private.json',[{'id':t} for t in ids])
            m={'cadence':{'loadSeconds':60},**({'staticTopology':{'kind':'static-hash-v1','workers':workers}} if workers else {})}
            with patch.object(a,'progress_services',return_value=services),patch.object(a,'compose',side_effect=compose):
                observer=a.observe_progress(d,m,d,'load');observer.observe()
        return observer,asked

    def test_each_static_slice_is_asked_only_for_its_share(self):
        observer,asked=self.run_load(2)
        self.assertIsNone(observer.failure)
        self.assertEqual(observer.rounds[0]['slices'],{'rule':'sha256-modulo-v1','count':2})
        self.assertEqual(sorted(t for _,chosen in asked for t in chosen),sorted(observer.ids))
        # Red: without the static topology every slice is asked for every tenant and refuses.
        observer,_=self.run_load(None)
        self.assertEqual(str(observer.failure),'M7_EVALUATOR_PROGRESS_UNAVAILABLE')

class ActualStages(unittest.TestCase):
    def test_local_compose_stage_receives_remaining_original_window(self):
        import contextlib
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
            root=Path(tmp);a.write(root/'frozen.compose.json',{'services':{}})
            m={'profile':'pgstream-sample','runPurpose':'discovery','generator':{'ready':True}}
            for name in ('frozen','experiment_host','verify','verify_generator','pin_service_images'):stack.enter_context(patch.object(a,name))
            stack.enter_context(patch.object(a,'image',return_value='synthetic'))
            stack.enter_context(patch.object(a,'deployment_plan',return_value=[('commission','compose',['run'])]))
            stage=stack.enter_context(patch.object(a,'compose',side_effect=RuntimeError('STOP_BEFORE_ACTOR')))
            stack.enter_context(patch.object(a.time,'time',return_value=1000));stack.enter_context(a.command_deadline(10000))
            with self.assertRaisesRegex(RuntimeError,'STOP_BEFORE_ACTOR'):a.deploy(root,m)
            self.assertEqual(stage.call_args.kwargs['timeout'],9000)

    def test_actual_discovery_prime_k6_and_probe_share_aged_cutoff(self):
        import contextlib,discovery,test_discovery
        fixture=test_discovery.Discovery();self.addCleanup(fixture.doCleanups)
        root,m=fixture.setup();m.update(profile='pgstream-sample',runPurpose='discovery',project='synthetic',port=1234,restartRoles=['api'],generator={'tools':{'node':{'path':'node'}}})
        a.write(root/'completion-source.json',{});record=discovery.Record(a,root,m);clock=[1000];waits=[]
        class Process:
            pid=12345;returncode=0
            def poll(self):return None
            def wait(self,timeout):waits.append(timeout);return 0
        def sleep(_):clock[0]+=700;(root/'load/.window').touch()
        with contextlib.ExitStack() as stack:
            for name in ('psql','phase_snapshot','job_record','stop_job','quiet','assert_owned','k6_tenants'):stack.enter_context(patch.object(a,name))
            for name in ('sampling','loadgen_process'):stack.enter_context(patch.object(a,name,return_value=contextlib.nullcontext()))
            stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']));stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
            stack.enter_context(patch.object(a.subprocess,'Popen',return_value=Process()))
            command=stack.enter_context(patch.object(a,'command'))
            stack.enter_context(patch.object(discovery,'observed_load',side_effect=lambda a,d,m,o,work:work()))
            stack.enter_context(patch.object(a.time,'time',side_effect=lambda:clock[0]));stack.enter_context(patch.object(a.time,'monotonic',side_effect=lambda:clock[0]));stack.enter_context(patch.object(a.time,'sleep',side_effect=sleep))
            stack.enter_context(a.command_deadline(10000));discovery.discovery_load(a,root,m,'k6',record)
        self.assertEqual(command.call_args.kwargs['timeout'],8300)
        self.assertEqual(waits,[8300,10])
        self.assertNotIn('prime',record.value['strictChecks'])

if __name__=='__main__':unittest.main()
