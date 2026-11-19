"""Bounded runner reuse: real finite actors, actual adapter.attach binding, no app stack."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import adapter as a
import runner as r

class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'session';self.root.mkdir()
        self.d=self.root/'fixture';self.d.mkdir();(self.root/'observations').mkdir()
        self.config={'prepare':{'fixture-project':'owned','diagnostic-resource-profile':a.diagnostic_resources.NAME,
            'image':'sha256:synthetic','core-commit':'core','deploy-commit':'deploy'},
            'k6Image':'k6','workSeconds':30,'cleanupSeconds':30}
        self.owner={'owner':'a'*32,'project':'owned','directory':str(self.d),'diagnosticResources':{'profile':a.diagnostic_resources.NAME}}
        a.write(self.d/'owner.json',self.owner);a.write(self.d/'frozen.compose.json',{});a.write(self.root/'config.json',self.config)
        self.state={'owner':'b'*32,'startedAt':time.time(),'stopWorkAt':time.time()+30,'cleanupAt':time.time()+60}
        a.write(self.root/'execution.json',self.state)
        self.session={**self.state,'runtimeOwner':self.owner['owner'],'runtimeOwnerSha256':a.digest(self.d/'owner.json'),
            'resourceCeiling':self.owner['diagnosticResources'],'cleanupRunner':str(Path(r.__file__).resolve())}
        a.write(self.root/'session.json',self.session)
        self.history=Path(self.tmp.name)/'history.json'
        a.write(self.history,{k:'retained synthetic fixture' for k in ('warmCache','seedHistory','previousWrites','restarts','activeViewers','elapsedAges')})
        self.calls=[]
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r,'execution_window',return_value=self.state))
        self.stack.enter_context(patch.object(r,'load_config',return_value=(self.config,[])))
        self.stack.enter_context(patch.object(a,'instrument',return_value={'sha256':'collector'}))
        self.stack.enter_context(patch.object(a.diagnostic_resources,'configure'))
        self.verify=self.stack.enter_context(patch.object(a,'verify'))
        self.stack.enter_context(patch.object(a,'image'))
        self.stack.enter_context(patch.object(a,'resources',return_value=[]))
        self.stage=self.stack.enter_context(patch.object(r,'stage',side_effect=self.perform))
    def perform(self,root,name,args):
        self.calls.append((name,args))
        if args[0]=='attach':
            d=Path(args[args.index('--directory')+1]);d.mkdir()
            a.write(d/'owner.json',{'attached':True,'project':'owned','owner':'c'*32})
            (d/'seed-witness').write_text((self.d/'seed-witness').read_text() if (self.d/'seed-witness').exists() else 'seed')
    def observe(self,name='first'):
        return r.session_observe(self.root,self.state['owner'],name,'config',self.history)
    def test_two_observations_retain_fixture_and_separate_history(self):
        (self.d/'seed-witness').write_text('original')
        self.observe();self.observe('second')
        self.assertEqual([args[0] for _,args in self.calls],['attach','preflight','run']*2)
        self.assertFalse((self.root/'cleanup.json').exists())
        self.assertEqual((self.d/'seed-witness').read_text(),'original')
        history=a.document(self.root/'observations/second/history.json')
        self.assertEqual(history['previousObservations'],['first'])
        self.assertEqual(history['runtime'],'REUSED')
        with self.assertRaisesRegex(RuntimeError,'OBSERVATION_EXISTS'):self.observe()
    def test_observer_attach_uses_validated_json_and_omits_prepare_only_options(self):
        selected={'roundSeconds':90}
        self.config['prepare']['opportunity-observation']=selected
        serialized=json.dumps(selected)
        argv=['--fixture-project','owned','--run-purpose','discovery','--opportunity-observation',serialized]
        with patch.object(r,'load_config',return_value=(self.config,argv)):
            self.observe()
        attached=next(args for _,args in self.calls if args[0]=='attach')
        self.assertEqual(attached[attached.index('--opportunity-observation')+1],serialized)
        self.assertNotIn('--fixture-project',attached)

    def test_failed_collection_retains_partial_and_can_collect_again(self):
        def failure(root,name,args):
            self.perform(root,name,args)
            if name=='first-run':
                a.write(self.root/'observations/first/fixture/summary.json',{'status':'PARTIAL'})
                raise RuntimeError('M7_COLLECTOR_FAILED')
        self.stage.side_effect=failure
        with self.assertRaisesRegex(RuntimeError,'OBSERVATION_INCOMPLETE'):self.observe()
        result=a.document(self.root/'observations/first/result.json')
        self.assertEqual(result['failure']['code'],'M7_COLLECTOR_FAILED')
        self.assertIn('summary.json',result['partial']['artifacts'])
        self.assertFalse((self.root/'cleanup.json').exists());self.observe('repair')
    def test_foreign_owner_changed_runtime_image_and_deadline_refused(self):
        with self.assertRaisesRegex(RuntimeError,'OWNER_REQUIRED'):r.session_access(self.root,'foreign')
        original=(self.d/'owner.json').read_bytes()
        a.write(self.d/'owner.json',{**self.owner,'imageId':'wrong'})
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_CHANGED'):self.observe()
        (self.d/'owner.json').write_bytes(original)
        self.config['prepare']['image']='wrong'
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_CONFIG_CHANGED'):self.observe()
        self.config['prepare']['image']='sha256:synthetic'
        self.state['stopWorkAt']+=1
        with self.assertRaisesRegex(RuntimeError,'WINDOW_CHANGED'):self.observe()
        self.state['stopWorkAt']-=1;self.observe()
    def test_interrupt_cleans_original_owner(self):
        self.stage.side_effect=KeyboardInterrupt()
        with patch.object(r,'session_close') as cleanup:
            with self.assertRaisesRegex(RuntimeError,'OBSERVATION_INCOMPLETE'):self.observe()
        cleanup.assert_called_once_with(self.root,self.state['owner'])
    def test_start_deploys_once_and_close_uses_original_runner(self):
        (self.root/'observations').rmdir()
        with patch.object(r,'prepare',return_value=self.root),patch.object(a,'load',return_value=(self.d,self.owner)):
            value=r.session_start('config',self.root)
        self.assertEqual([args[0] for _,args in self.calls],['deploy'])
        self.assertEqual(value['cleanupAt'],self.state['cleanupAt'])
        with patch.object(r.subprocess,'run') as command:
            r.session_close(self.root,self.state['owner'])
            self.assertEqual(command.call_args.args[0],[sys.executable,'-B',value['cleanupRunner'],'down',str(self.root)])
            with self.assertRaisesRegex(RuntimeError,'OWNER_REQUIRED'):r.session_close(self.root,'foreign')
            self.assertEqual(command.call_count,1)

    def test_default_execute_still_cleans_at_point_end(self):
        a.write(self.root/'result.json',{'status':'PREPARED'})
        with patch.object(a,'load',return_value=(self.d,self.owner)),patch.object(r,'cleanup') as cleanup,patch.object(r,'guard_alive',return_value=False):
            r.execute(self.root)
        cleanup.assert_called_once_with(self.root,'POINT_FINISHED')

    def test_collector_cleanup_stops_its_actual_child_preserving_runtime_actor(self):
        actors=[subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True) for _ in range(2)]
        try:
            ob=self.root/'observations/one';d=ob/'fixture';(d/'load').mkdir(parents=True)
            a.write(d/'owner.json',{'attached':True,'owner':'collector','project':'owned'})
            a.job_record(d/'load/probe-job.json',actors[1],'collector')
            r.stop_session_collectors(self.root)
            actors[1].wait(timeout=3)
            self.assertIsNone(actors[0].poll())
            self.assertEqual(actors[1].returncode,-signal.SIGTERM)
        finally:
            for actor in actors:
                if actor.poll() is None:os.killpg(actor.pid,signal.SIGKILL);actor.wait()

    def test_term_receipt_does_not_hide_a_live_collector(self):
        ready=Path(self.tmp.name)/'ready'
        child=subprocess.Popen([sys.executable,'-c',
            "import pathlib,signal,time,sys;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(sys.argv[1]).touch();time.sleep(30)",str(ready)])
        try:
            until=time.monotonic()+3
            while not ready.exists() and time.monotonic()<until:time.sleep(.01)
            self.assertTrue(ready.exists())
            job=Path(self.tmp.name)/'job.json';a.job_record(job,child,'collector')
            a.stop_job(job,'collector')
            self.assertTrue(a.document(job)['completed']);self.assertIsNone(child.poll())
            r.stop_stage(job,'collector');child.wait(timeout=3)
            self.assertEqual(child.returncode,-signal.SIGKILL)
        finally:
            if child.poll() is None:child.kill();child.wait()

    def test_original_guard_expires_and_cleanup_is_idempotent(self):
        # No fixture owner in this real subprocess case: exact finite host actor only.
        root=Path(self.tmp.name)/'finite';root.mkdir()
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
        try:
            a.job_record(root/'stage-job.json',child,'owner',group=True)
            a.write(root/'execution.json',{'owner':'owner','stopWorkAt':time.time()+.1,'cleanupAt':time.time()+10})
            guard=subprocess.run([sys.executable,'-B',r.__file__,'_guard',str(root)],capture_output=True,timeout=15)
            self.assertEqual(guard.returncode,0,guard.stderr.decode());child.wait(timeout=3)
            original=(root/'cleanup.json').read_bytes()
            r.cleanup(root,'SECOND_CLOSE');self.assertEqual((root/'cleanup.json').read_bytes(),original)
            self.assertEqual(a.document(root/'cleanup.json')['reason'],'FINITE_DEADLINE')
        finally:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait()


class ActualAttachment(unittest.TestCase):
    def test_profile_driver_is_configured_only_after_canonical_owner_binding(self):
        from test_attach_dependencies import AttachmentDependencies
        fixture=AttachmentDependencies();fixture.setUp()
        try:
            record={'profile':a.diagnostic_resources.NAME}
            fixture.owner['diagnosticResources']=record;fixture.m['diagnosticResources']=record;fixture.save()
            a.write(fixture.target/'frozen.compose.json',{})
            with patch.object(a.diagnostic_resources,'configure') as configure:
                fixture.m['runtimeOwnerLabels']=['foreign']
                with self.assertRaisesRegex(RuntimeError,'RUNTIME_OWNER_MISMATCH'):fixture.run_binding()
                configure.assert_not_called()
                fixture.m['runtimeOwnerLabels']=[fixture.owner['owner']]
                fixture.run_binding()
                self.assertEqual(configure.call_args.args[:3],(record['profile'],{},record))
        finally:fixture.doCleanups()

    def test_attach_calls_preserve_seed_and_bind_profile_and_external_topology(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime=root/'runtime';runtime.mkdir()
            for name in ('core','state','dependencies'):(runtime/name).mkdir()
            (runtime/'state/primer').mkdir();(runtime/'state/primer/tenants.json').write_text('[]')
            (runtime/'state/seed').write_text('unchanged')
            (runtime/'env').write_text('synthetic');(runtime/'compose.json').write_text('{}')
            profile={'profile':a.diagnostic_resources.EXTERNAL_NAME,'synthetic':'exact ceiling'}
            edge_budget={'workerProcesses':1,'workerConnections':16384,'nginxMillicpus':125,
                'configurationSha256':'a'*64}
            a.write(runtime/'owner.json',{'edgeWorkerBudget':edge_budget,'diagnosticResources':profile,'directory':str(runtime),'prepared':True,
                'project':'synthetic','pair':{'core':'core','deploy':'deploy'},'imageId':'sha256:'+'e'*64})
            config={'services':{'nginx':{'ports':[{'host_ip':'127.0.0.1','published':12345}]},
                'vault':{'command':['vault','server']},'pgstream':{'command':a.stream_topology.EXTERNAL_COMMAND},'evaluator':{'command':['evaluator']}}}
            row={'Id':'physical','Image':'sha256:'+'e'*64,'State':{'StartedAt':'original'},
                'Config':{'Labels':{a.OWNER:'original','com.docker.compose.service':'evaluator'}}}
            args=SimpleNamespace(fixture_project=None,profile='pgstream-sample',run_purpose='discovery',
                core_repo=str(runtime/'core'),core_commit='core',deploy_repo='deploy',deploy_commit='deploy',
                source_root=str(runtime/'core'),state=str(runtime/'state'),dependencies_root=str(runtime/'dependencies'),
                project='synthetic',image='sha256:'+'e'*64,image_id='sha256:'+'e'*64,tenants=1,replicas=1,freeze=str(root/'receipt.json'),
                quiet_load=0,env_file=str(runtime/'env'),compose=[str(runtime/'compose.json')],
                runtime_owner=str(runtime/'owner.json'),pgstream_topology=a.stream_topology.EXTERNAL)
            with ExitStack() as stack:
                for name,value in {'instrument':{'sha256':'d'*64},'git':'core','resources':[row],
                    'fixture_inventory':{},'host_identity':{},'generate':{},'generate_workload':{},
                    'tenant_projection':[]}.items():
                    stack.enter_context(patch.object(a,name,return_value=value))
                stack.enter_context(patch.object(a,'commit',side_effect=lambda repo,head:head))
                stack.enter_context(patch.object(a.diagnostic_resources,'configure'))
                def bind(d,source,dependencies,m,owner_file):
                    self.assertNotIn('edgeWorkerBudget',m)
                    return {'runtimeOwner':{'owner':'original'}}
                stack.enter_context(patch.object(a,'attachment_generator',side_effect=bind))
                actual_frozen=a.frozen
                def admission(m,operation):
                    import run_configuration as rc
                    receipt={'version':2,'kind':'joined-diagnostic','status':'AUTHORIZED_DIAGNOSTIC',
                        'purpose':'BOUNDED_DISCOVERY','pair':m['pair'],'imageId':m['imageId'],'instrument':'d'*64,
                        'functionalAcceptanceAtAuthorization':'PENDING','sourceAcceptance':{'status':'PENDING'},
                        'configurationSha256':rc.sha(m['runConfiguration']),
                        'execution':{'workSeconds':3600,'cleanupSeconds':30,'k6Image':'sha256:'+'f'*64},
                        'limits':{'tenants':1,'apiReplicas':1,'trafficSeconds':m['cadence']['loadSeconds']}}
                    a.write(root/'receipt.json',receipt)
                    return actual_frozen(m,operation)
                stack.enter_context(patch.object(a,'frozen',side_effect=admission));stack.enter_context(patch.object(a,'image'))
                stack.enter_context(patch.object(a,'serving_mounts'))
                stack.enter_context(patch.object(a,'command',side_effect=lambda argv,**kw:json.dumps(config if 'config' in argv else dict(schema='synthetic',sha256='synthetic',sourceCommit='core',sourceBlobs={}))))
                def verify(d,m):
                    self.assertEqual(m['diagnosticResources'],profile)
                    owner=a.document(runtime/'owner.json')
                    if 'edgeWorkerBudget' in owner:self.assertEqual(m.get('edgeWorkerBudget'),edge_budget)
                    else:self.assertNotIn('edgeWorkerBudget',m)
                    self.assertEqual(a.stream_topology.verify_config(m,config),a.stream_topology.EXTERNAL)
                stack.enter_context(patch.object(a,'verify',side_effect=verify))
                for name in ('one','two'):
                    args.directory=str(root/name);a.attach(args)
                    m=a.document(root/name/'owner.json')
                    self.assertEqual(m['attachedResources']['physical']['startedAt'],'original')
                    self.assertTrue((root/name/'state').is_symlink())
                    actual_frozen(m,'run')
                    receipt=a.document(root/'receipt.json');receipt['configurationSha256']='0'*64
                    a.write(root/'receipt.json',receipt)
                    with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH'):actual_frozen(m,'run')
                    owner=a.document(runtime/'owner.json');owner.pop('edgeWorkerBudget',None)
                    a.write(runtime/'owner.json',owner)
            self.assertEqual((runtime/'state/seed').read_text(),'unchanged')

if __name__=='__main__':unittest.main()
