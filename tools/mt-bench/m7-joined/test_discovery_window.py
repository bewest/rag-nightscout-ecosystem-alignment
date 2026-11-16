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
            for name in ('psql','phase_snapshot','job_record','stop_job','quiet','assert_owned'):stack.enter_context(patch.object(a,name))
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
