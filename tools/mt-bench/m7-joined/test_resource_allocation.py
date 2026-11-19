"""Explicit allocation through canonical quotas and real controller/worker/parser."""
import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import adapter as a
import diagnostic_resources as r

ROLES=('postgres','vault','admin','primer','api','realtime','evaluator','tenant-admin','ui','nginx','pgstream')

def allocation():
    return {'version':1,'services':{role:{'millicpus':r.role_limit(role,r.QUALIFICATION_NAME).cpu,'memoryBytes':r.role_limit(role,r.QUALIFICATION_NAME).memory} for role in ROLES},'driver':{'millicpus':2000,'memoryBytes':4*1024**3},'ceiling':{'millicpus':16000,'memoryBytes':32*1024**3},'edge':{'workerProcesses':1,'workerConnections':16384}}

def expanded_allocation():
    selected=allocation()
    selected['services']['postgres']={'millicpus':65001,'memoryBytes':129*1024**3}
    for role in [*(f'api-{i}' for i in range(2,17)),*(f'evaluator-{i}' for i in range(2,9))]:
        selected['services'][role]={'millicpus':1000,'memoryBytes':128*r.MIB}
    selected['ceiling']={'millicpus':100000,'memoryBytes':160*1024**3}
    selected['edge']={'workerProcesses':65,'workerConnections':65536}
    return selected


def supported_allocation():
    # Explicit synthetic selections on the measured runtime's precision grid.
    selected=expanded_allocation()
    for limit in selected['services'].values():limit['millicpus']=1000
    selected['services']['postgres']['millicpus']=65010
    selected['ceiling']['millicpus']=200000
    return selected


def runtime_reader(driver='systemd', version='1.3.3-0ubuntu1~24.04.3', default='runc'):
    def read(argv):
        if argv[1]=='info':return json.dumps({'CgroupDriver':driver,'CgroupVersion':'2','DefaultRuntime':default,'ServerVersion':'29.1.3'})
        if argv[1]=='version':return json.dumps([{'Name':'runc','Version':version}])
        raise AssertionError('unexpected daemon read')
    return read


def matched_allocation():
    # Resource-only synthetic counterpart of the retained preload18 allocation.
    dimensions={'admin':(1500,512),'api':(3000,4096),'bootstrap':(500,512),'demo':(125,256),
        'evaluator':(4000,2048),'nginx':(250,256),'pgstream':(1000,512),
        'placement-operator':(125,128),'postgres':(4000,2560),'primer':(1000,1024),
        'realtime':(2000,2048),'socket-edge':(250,256),'tenant-admin':(250,512),
        'ui':(250,256),'vault':(250,512)}
    return {'version':1,'services':{role:{'millicpus':cpu,'memoryBytes':memory*r.MIB}for role,(cpu,memory)in dimensions.items()},
        'driver':{'millicpus':4000,'memoryBytes':8192*r.MIB},'ceiling':{'millicpus':24000,'memoryBytes':26624*r.MIB},
        'edge':{'workerProcesses':1,'workerConnections':16384}}


def matched_source(selected):
    dependencies={'admin':['postgres','vault'],'api':['postgres','vault'],'bootstrap':['postgres','vault'],
        'evaluator':['realtime'],'nginx':['api','realtime','socket-edge','ui'],'pgstream':['evaluator','postgres'],
        'primer':['admin'],'realtime':['api'],'tenant-admin':['api','postgres','vault']}
    services={role:{'command':(['postgres']if role=='postgres'else a.stream_topology.EXTERNAL_COMMAND if role=='pgstream'
        else a.static_topology.EDGE_COMMAND if role=='socket-edge'else ['node','entrypoint.js',role]),
        'depends_on':{dep:{'condition':'service_started'}for dep in dependencies.get(role,[])},
        **({'profiles':['ops']}if role in ('bootstrap','primer','demo','placement-operator')else {})}for role in selected['services']}
    return {'services':services}


def prepare_stage_control(selected, observation, source=None):
    """Actual owned preparer with inert source/Compose ports; no native actors."""
    import experiment_batch
    from test_edge_workers import TEXT
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder)/'fixture';d.mkdir();render=copy.deepcopy(source or matched_source(selected))
        args=SimpleNamespace(core_repo='core',deploy_repo='deploy',core_commit='a'*40,deploy_commit='b'*40,
            image='sha256:'+'c'*64,postgres_image='sha256:'+'d'*64,tenants=1000,replicas=1,quiet_load=3,
            freeze=str(d/'freeze.json'),profile='pgstream-sample',run_purpose='discovery',
            backend_subnet='10.221.0.0/28',edge_subnet='10.221.1.0/28',fixture_project='ns-cpu-fixture',
            diagnostic_resource_profile=None,diagnostic_resource_allocation=selected,
            diagnostic_cpu_preflight=observation,pgstream_topology=a.stream_topology.EXTERNAL)
        for role,spec in render['services'].items():spec['image']=args.postgres_image if role=='postgres'else args.image
        def git(repo,*argv):
            if argv[:2]==('worktree','add'):(d/'core/deploy/multitenant').mkdir(parents=True)
            return ''
        def command(argv,**options):
            if argv[0]=='git'and 'archive'in argv:return b''
            if argv[0]=='tar':
                overlay=d/'core/deploy/multitenant'
                for name in ('compose.yaml','commission-restore.js','publish-primer.js'):(overlay/name).write_text('synthetic')
                return ''
            if argv[0]=='node':
                (d/'core/deploy/multitenant/.env').write_text('SYNTHETIC=1\n')
                edge=d/'state/edge';edge.mkdir(parents=True);(edge/'nginx.conf').write_text(TEXT);return ''
            if argv[0]=='docker'and argv[1]in ('network','volume'):return ''
            if argv[:2]==['docker','compose']and 'config'in argv:return json.dumps(render)
            raise AssertionError('unexpected command at inert prepare port:'+str(argv[:2]))
        with patch.object(experiment_batch,'global_lock_path',return_value=Path(folder)/'unit-heap.lock'):
            r.configure(selected)
            try:
                with patch.object(a,'setup_generator'),patch.object(a,'seal_diagnostic_images',side_effect=lambda config,m:config), \
                     patch.object(a,'port',return_value=12345),patch.object(a,'git',side_effect=git), \
                     patch.object(a,'command',side_effect=command),patch.object(a,'frozen'), \
                     patch.object(a.static_topology,'verify_config'), \
                     patch.object(a,'inventory',return_value={}),patch.object(a,'host_identity',return_value='host'), \
                     patch.object(a,'resources',return_value=[]):a.prepare_staged(args,d,{'sha256':'e'*64})
                return a.document(d/'owner.json'),a.document(d/'frozen.compose.json')
            finally:r.configure()

class ExplicitAllocation(unittest.TestCase):
    def test_matched_dormant_125m_roles_remain_deferred_and_activation_refuses(self):
        selected=matched_allocation();original=copy.deepcopy(selected)
        observation=r.fresh_cpu_preflight(selected,runtime_reader(),roles=())
        with contextlib.redirect_stdout(io.StringIO()):owner,config=prepare_stage_control(selected,observation)
        scoped=owner['cpuPrecisionPreflight']
        self.assertEqual(scoped['verdict'],'PASS')
        self.assertEqual(scoped['deferredRoles'],['demo','placement-operator'])
        self.assertEqual(set(scoped['qualifiedRoles']),set(selected['services'])-{'demo','placement-operator'})
        self.assertTrue({'bootstrap','primer'}<=set(scoped['qualifiedRoles']))
        self.assertEqual(selected,original)
        self.assertEqual(owner['diagnosticResources']['profile'],original)
        self.assertNotIn('aggregate', owner['diagnosticResources'])
        for role in scoped['deferredRoles']:
            self.assertEqual((config['services'][role]['cpu_quota'],config['services'][role]['cpu_period']),(12500,100000))
            runtime=r.Runtime(config,owner['diagnosticResources'],lambda:[])
            output=io.StringIO()
            def document(path):return owner if Path(path).name=='owner.json'else config
            with patch.object(r,'_ACTIVE',runtime),patch.object(a,'document',side_effect=document), \
                 patch.object(a.orchestration_binding,'fixture_argv',return_value=['docker','compose','run',role]), \
                 patch.object(a.orchestration_binding,'fixture_mutation_preflight'), \
                 patch.object(a,'command') as launch, \
                 contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(RuntimeError,'CPU_UNREPRESENTABLE:services.'+role+'.millicpus'):
                    a.compose(Path('/synthetic'),'--profile','ops','run','--rm','--no-deps',role)
                launch.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['diagnostic']['millicpus'],125)
        # Existing active actors are part of the admission census too; an
        # unsupported dormant actor cannot hide behind a different target.
        role='demo';spec=config['services'][role]
        row={'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':role}},
             'HostConfig':{'NanoCpus':0,'CpuQuota':spec['cpu_quota'],'CpuPeriod':spec['cpu_period'],
                           'Memory':spec['mem_limit'],'MemorySwap':spec['memswap_limit']}}
        runtime=r.Runtime(config,owner['diagnosticResources'],lambda:[row])
        with self.assertRaisesRegex(RuntimeError,'CPU_UNREPRESENTABLE:services.demo.millicpus'):
            runtime.compose(['up','-d','--no-deps','postgres'],config,scoped)

    def test_actual_execution_active_and_transitive_precision_refuse_without_rounding(self):
        selected=matched_allocation();selected['services']['postgres']['millicpus']=65001;selected['ceiling']['millicpus']=100000
        observation=r.fresh_cpu_preflight(selected,runtime_reader(),roles=())
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'CPU_UNREPRESENTABLE:services.postgres.millicpus'):
            prepare_stage_control(selected,observation)
        selected=matched_allocation();source=matched_source(selected)
        source['services']['postgres']['depends_on']={'demo':{'condition':'service_started'}}
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'CPU_UNREPRESENTABLE:services.demo.millicpus'):
            prepare_stage_control(selected,r.fresh_cpu_preflight(selected,runtime_reader(),roles=()),source)
        self.assertEqual(selected['services']['demo']['millicpus'],125)
        self.assertIn('demo',r.compose_actor_roles(['up','-d','postgres'],source))
        self.assertEqual(r.compose_actor_roles(['up','-d','--no-deps','postgres'],source),['postgres'])
        self.assertEqual(r.compose_actor_roles(['--profile','ops','run','--rm','--no-deps','primer','node','demo'],source),['primer'])
        # No explicit targets means actual Compose profile activation, rather
        # than an exemption of all ops-profile services.
        self.assertTrue({'demo','placement-operator'}<=set(r.compose_actor_roles(['--profile','ops','up','-d'],source)))

    def test_actual_cli_preserves_safe_code_and_bounded_failure_evidence(self):
        from test_run_configuration import config
        import runner
        selected=matched_allocation();selected['services']['postgres']['millicpus']=65001;selected['ceiling']['millicpus']=100000
        cfg=config();cfg['prepare'].pop('diagnostic-resource-profile',None)
        cfg['prepare'].update({'diagnostic-resource-allocation':selected,
            'pgstream-topology':'external-service-v1','generator-dependencies':'/synthetic/dependencies'})
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):_,argv=runner.validate_config(cfg)
        # Execute the actual CLI main/parser/footer with the actual owned
        # preparer behind inert source/Compose ports. Qualification occurs
        # after render and before any native actor command.
        code="""import ast,pathlib,sys,adapter as a
from test_resource_allocation import runtime_reader,prepare_stage_control
import diagnostic_resources as r
a.prepare=lambda args:prepare_stage_control(args.diagnostic_resource_allocation,
    r.fresh_cpu_preflight(args.diagnostic_resource_allocation,runtime_reader(),roles=()))
sys.argv=['adapter.py',*sys.argv[1:]]
footer=ast.parse(pathlib.Path(a.__file__).read_text()).body[-1]
exec(compile(ast.Module(body=footer.body,type_ignores=[]),a.__file__,'exec'),a.__dict__)
"""
        with tempfile.TemporaryDirectory() as area:
            target=Path(area)/'uncreated'
            actual=subprocess.run([sys.executable,'-B','-c',code,'prepare','--directory',str(target),*argv],
                cwd=a.HERE,capture_output=True,text=True,timeout=20)
        expected='M7_DIAGNOSTIC_RESOURCE_CPU_UNREPRESENTABLE:services.postgres.millicpus'
        self.assertEqual(actual.returncode,1,actual.stderr)
        self.assertEqual(actual.stderr.strip(),expected)
        self.assertEqual(runner.code(RuntimeError(expected)),expected)
        self.assertLess(len(actual.stdout.encode()),4096)
        evidence=json.loads(actual.stdout)
        self.assertEqual(set(evidence),{'kind','verdict','code','diagnostic'})
        self.assertEqual(evidence['code'],expected)
        self.assertEqual(evidence['diagnostic']['reason'],'WHOLE_PERCENT_CPU_REQUIRED')
        self.assertEqual(evidence['diagnostic']['runtime']['runcVersion'],'1.3.3-0ubuntu1~24.04.3')
        self.assertEqual(evidence['diagnostic']['millicpus'],65001)

    def test_fresh_owner_records_pass_and_unmeasured_runtime_observation(self):
        import experiment_batch
        import test_edge_workers as edge
        for observation in (r.fresh_cpu_preflight(supported_allocation(),runtime_reader()),
                            r.fresh_cpu_preflight(supported_allocation())):
            recorded=[];original=a.write
            def write(path,value):
                if Path(path).name=='owner.json':recorded.append(copy.deepcopy(value))
                return original(path,value)
            with tempfile.TemporaryDirectory() as folder, \
                 patch.object(experiment_batch,'global_lock_path',return_value=Path(folder)/'unit-heap.lock'), \
                 patch.object(edge,'SimpleNamespace',side_effect=lambda **kw:SimpleNamespace(diagnostic_cpu_preflight=observation,**kw)), \
                 patch.object(a,'write',side_effect=write):
                edge.EdgeWorkers().test_actual_prepare_forwards_and_records_generated_workers()
            self.assertTrue(recorded)
            self.assertEqual(recorded[-1]['cpuPrecisionPreflight'],observation)

    def test_actual_prepare_observes_runtime_only_and_plans_remain_pure(self):
        selected=supported_allocation();selected['services']['postgres']['millicpus']=65001
        args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',backend_subnet=None,
                             directory='/synthetic/fixture',diagnostic_resource_profile=None,diagnostic_resource_allocation=selected,
                             generator_dependencies='/synthetic/dependencies')
        with patch.object(a,'command',side_effect=lambda argv,**_:runtime_reader()(argv)) as reads, \
             patch.object(a,'prepare_staged') as effects, \
             patch.object(a.diagnostic_resources,'configure',side_effect=AssertionError('effect boundary reached')) as leases:
            with self.assertRaisesRegex(AssertionError,'effect boundary reached'):a.prepare(args)
            self.assertEqual(reads.call_count,2);effects.assert_not_called();leases.assert_called_once()
        self.assertEqual(args.diagnostic_cpu_preflight['verdict'],'UNMEASURED')
        self.assertEqual(args.diagnostic_cpu_preflight['qualifiedRoles'],[])
        # A real prepare opt-in does not contaminate shared/offline resolution,
        # even for an actual parser Namespace whose command is "prepare".
        args.command='prepare'
        with patch.object(a,'command',side_effect=AssertionError('plan queried daemon')):
            self.assertEqual(a.selected_resources_profile(args),selected)
            self.assertEqual(r.fresh_cpu_preflight(selected)['verdict'],'UNMEASURED')
        from test_run_configuration import config
        import run_configuration
        cfg=config();cfg['prepare'].pop('diagnostic-resource-profile',None)
        cfg['prepare']['diagnostic-resource-allocation']=selected
        cfg['prepare']['pgstream-topology']='external-service-v1'
        cfg['prepare']['generator-dependencies']='/synthetic/dependencies'
        with patch.object(a,'command',side_effect=AssertionError('resolver queried daemon')) as daemon, \
             patch.object(a,'instrument',return_value={'sha256':'d'*64}):
            planned=run_configuration.resolve(cfg,{'status':'PENDING'})
            import runner
            cfg['tier']='discovery'
            tier=runner.tier_plan(cfg)
            daemon.assert_not_called()
        self.assertEqual(planned['configuration']['resources']['profile'],selected)
        self.assertEqual(tier['effective']['resources']['profile'],selected)

    def test_runtime_precision_is_scoped_and_never_rounds_selected_resources(self):
        selected=supported_allocation();original=copy.deepcopy(selected)
        self.assertEqual(r.fresh_cpu_preflight(selected,runtime_reader())['verdict'],'PASS')
        self.assertEqual(selected,original)
        for cpu in (1,9,125,65001,r.MAX_DRIVER_MILLICPUS):
            bad=copy.deepcopy(selected);bad['services']['postgres']['millicpus']=cpu
            bad['ceiling']['millicpus']=cpu+100000
            with self.assertRaisesRegex(RuntimeError,'CPU_UNREPRESENTABLE:services.postgres.millicpus'):
                r.fresh_cpu_preflight(bad,runtime_reader())
            for reader in (runtime_reader(driver='cgroupfs'),runtime_reader(version='unqualified'),runtime_reader(default='other'),lambda _: '{}'):
                self.assertEqual(r.fresh_cpu_preflight(bad,reader)['verdict'],'UNMEASURED')
            self.assertEqual(r.selection(bad),bad)
        for value in (None,r.QUALIFICATION_NAME):
            self.assertEqual(r.fresh_cpu_preflight(value,lambda _:self.fail('legacy/default queried daemon'))['verdict'],'NOT_APPLICABLE')
        self.assertEqual(r.fresh_cpu_preflight(selected,lambda _:(_ for _ in ()).throw(RuntimeError('unavailable')))['verdict'],'UNMEASURED')
        self.assertEqual(r.fresh_cpu_preflight(selected,lambda _:(_ for _ in ()).throw(subprocess.TimeoutExpired('docker',1)))['verdict'],'UNMEASURED')

    def test_runc_conversion_product_bounds_and_old_frozen_period_remain_exact(self):
        boundary=r.MAX_RUNC_SYSTEMD_QUOTA_US//100
        self.assertEqual(r.service_cpu_settings(boundary),(boundary*100,100000))
        self.assertEqual(r.service_cpu_settings(boundary+1),(boundary+1,1000))
        selected=supported_allocation();maximum=r.MAX_RUNC_SYSTEMD_QUOTA_US//10*10
        selected['services']['postgres']['millicpus']=maximum;selected['ceiling']['millicpus']=maximum+100000
        self.assertEqual(r.fresh_cpu_preflight(selected,runtime_reader())['verdict'],'PASS')
        selected['services']['postgres']['millicpus']=maximum+10;selected['ceiling']['millicpus']+=10
        with self.assertRaisesRegex(RuntimeError,'CPU_UNREPRESENTABLE:services.postgres.millicpus') as caught:
            r.fresh_cpu_preflight(selected,runtime_reader())
        self.assertEqual(caught.exception.diagnostic['reason'],'SIGNED_QUOTA_PRODUCT_OVERFLOW')
        # This pair was produced by 604's larger Linux-only threshold. Keep
        # its record/readback unchanged rather than rewriting an entered scope.
        selected=supported_allocation();cpu=100000000000;selected['services']['postgres']['millicpus']=cpu
        selected['ceiling']['millicpus']=cpu+100000
        config=r.overlay({'services':{role:{} for role in selected['services']}},selected)
        spec=config['services']['postgres'];spec.update(cpu_quota=cpu*100,cpu_period=100000)
        budget=r.plan(config);r.verify_config(config,budget)
        self.assertEqual(budget.record()['services']['postgres']['cpuEnforcement']['periodMicros'],100000)
        host={'NanoCpus':0,'CpuQuota':cpu*100,'CpuPeriod':100000,'Memory':spec['mem_limit'],'MemorySwap':spec['memswap_limit']}
        runtime=r.Runtime(config,budget.record(),lambda:[{'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':'postgres'}},'HostConfig':host}])
        runtime.containers();host.update(CpuQuota=cpu,CpuPeriod=1000)
        with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
        broken=copy.deepcopy(config);broken['services']['postgres'].update(cpu_quota=cpu,cpu_period=1000)
        with self.assertRaisesRegex(RuntimeError,'PLAN_CHANGED'):r.verify_config(broken,budget)

    def test_captured_native17_and_period_hypothesis_remain_strict_red(self):
        selected=supported_allocation();selected['services']['evaluator']['millicpus']=65001
        memory=str(selected['services']['evaluator']['memoryBytes'])
        for actual,expected in (('6501000 100000',(6500100,100000)),('65010000 1000000',(65001000,1000000))):
            with self.assertRaisesRegex(RuntimeError,'EFFECTIVE_CPU_CHANGED'):
                r.verify_evaluator_cgroup(selected,actual,memory,'0',expected_cpu=expected)
        selected['services']['evaluator']['millicpus']=65010
        self.assertEqual(r.verify_evaluator_cgroup(selected,'6501000 100000',memory,'0')['millicpus'],65010)
        selected['services']['evaluator']['millicpus']=10
        self.assertEqual(r.verify_evaluator_cgroup(selected,'1000 100000',memory,'0')['millicpus'],10)

    def test_explicit_sizes_and_roster_follow_allocation_not_reference_maxima(self):
        selected=expanded_allocation()
        self.assertEqual(len(selected['services']),33)
        config=r.overlay({'services':{role:{} for role in selected['services']}},selected)
        budget=r.plan(config);r.verify_config(config,budget)
        self.assertNotIn('cpus',config['services']['postgres'])
        self.assertEqual(config['services']['postgres']['cpu_quota'],6500100)
        self.assertEqual(config['services']['postgres']['cpu_period'],100000)
        self.assertEqual(config['services']['postgres']['mem_limit'],129*1024**3)
        bad=copy.deepcopy(selected);bad['ceiling']['millicpus']=1
        self.assertEqual(r.selection(bad), bad)
        del bad['ceiling']
        self.assertEqual(r.plan(r.overlay({'services':{role:{} for role in bad['services']}},bad)).profile, bad)
        r.selection(selected)

    def test_native_representation_edge_and_aggregate_controls_restore(self):
        selected=expanded_allocation()
        controls=(
            (lambda x:x['services']['postgres'].update(millicpus=r.MAX_ALLOCATION_MILLICPUS+1),'CPU_INVALID'),
            (lambda x:x['services']['postgres'].update(memoryBytes=r.NATIVE_INT64_MAX+1),'MEMORY_INVALID'),
            (lambda x:x['edge'].update(workerProcesses=r.NGINX_MAX_WORKERS+1),'ALLOCATION_EDGE'),
            (lambda x:x['edge'].update(workerConnections=r.EDGE_NOFILE+1),'ALLOCATION_EDGE_DESCRIPTOR_LIMIT'),
            (lambda x:x['edge'].update(workerConnections=True),'ALLOCATION_EDGE'),
            (lambda x:x['edge'].update(workerProcesses=True),'ALLOCATION_EDGE'),
            (lambda x:x['services'].update({'api-17':{'millicpus':1000,'memoryBytes':128*r.MIB}}),'UNKNOWN_ROLE'),
        )
        for change,code in controls:
            with self.subTest(code=code):
                bad=copy.deepcopy(selected);change(bad)
                with self.assertRaisesRegex(RuntimeError,code):r.selection(bad)
                self.assertEqual(r.selection(selected),selected)
        print('RED_RESTORED native int64, process table, retained descriptor budget, role roster and aggregate controls')

    def test_remote_receiver_matches_explicit_resources_and_retains_host_fit(self):
        path=a.HERE.parent/'remote-pgstream/protocol.py'
        loader=importlib.util.spec_from_file_location('resource_protocol_control',path)
        protocol=importlib.util.module_from_spec(loader);loader.loader.exec_module(protocol)
        selected=expanded_allocation()
        hosts={'sut':{'cpuCores':128,'ramBytes':160*1024**3},'driver':{'cpuCores':4,'ramBytes':8*1024**3}}
        self.assertEqual(protocol.allocation_boundary(selected,hosts),r.selection(selected))
        for host,key,value in (('sut','cpuCores',64),('sut','ramBytes',128*1024**3),('driver','cpuCores',1),('driver','ramBytes',2*1024**3)):
            bad=copy.deepcopy(hosts);bad[host][key]=value
            with self.assertRaisesRegex(RuntimeError,'REMOTE_ALLOCATION_HOST_CAPACITY'):protocol.allocation_boundary(selected,bad)
            protocol.allocation_boundary(selected,hosts)
        for change in (lambda x:x['edge'].update(workerProcesses=0),lambda x:x['edge'].update(workerConnections=65537),lambda x:x['services']['postgres'].update(millicpus=r.MAX_ALLOCATION_MILLICPUS+1),lambda x:x['services']['postgres'].update(memoryBytes=r.NATIVE_INT64_MAX+1)):
            bad=copy.deepcopy(selected);change(bad)
            with self.assertRaisesRegex(RuntimeError,'REMOTE_ALLOCATION_'):protocol.allocation_boundary(bad,hosts)
            protocol.allocation_boundary(selected,hosts)
        print('RED_RESTORED remote receiver native fields and actual SUT/driver inventory fit')

    def test_authored_allocation_replaces_reference_but_readback_still_refuses(self):
        selected=allocation();selected['services']['api']={'millicpus':3000,'memoryBytes':4*1024**3}
        source={'services':{role:{} for role in ROLES}}
        source['services']['api'].update(cpus=.25,mem_limit=512*1024**2,memswap_limit=512*1024**2)
        original=copy.deepcopy(source)
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):
            r.overlay(source,r.QUALIFICATION_NAME)
        applied=r.overlay(source,selected)
        self.assertEqual(source,original)
        self.assertNotIn('cpus',applied['services']['api'])
        self.assertEqual(applied['services']['api']['cpu_quota'],300000)
        self.assertEqual(applied['services']['api']['cpu_period'],100000)
        self.assertEqual(applied['services']['api']['mem_limit'],4*1024**3)
        self.assertEqual(applied['services']['api']['memswap_limit'],4*1024**3)
        budget=r.plan(applied);r.verify_config(applied,budget)
        broken=copy.deepcopy(applied);broken['services']['api']['cpu_quota']+=1
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(broken,budget)
        r.verify_config(applied,budget)
        print('RED_RESTORED reference conflict; explicit allocation replaces; changed actual limit refuses')

    def test_exact_roster_overlap_and_driver_native_quota_controls(self):
        selected=allocation();source={'services':{role:{} for role in ROLES}};config=r.overlay(source,selected);budget=r.plan(config)
        self.assertEqual(source,{'services':{role:{} for role in ROLES}})
        self.assertNotIn('aggregate', budget.record())
        self.assertEqual(budget.record()['standalone']['k6']['millicpus'],2000)
        self.assertEqual(r.edge_worker_budget(selected),{'workerProcesses':1,'workerConnections':16384,'nginxMillicpus':125,'source':'explicit-resource-allocation-v1'})
        rows=[{'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':role}},'HostConfig':{'NanoCpus':0,'CpuQuota':r.service_cpu_settings(selected['services'][role]['millicpus'])[0],'CpuPeriod':r.service_cpu_settings(selected['services'][role]['millicpus'])[1],'Memory':selected['services'][role]['memoryBytes'],'MemorySwap':selected['services'][role]['memoryBytes']}} for role in ROLES]
        runtime=r.Runtime(config,budget.record(),lambda:rows)
        runtime.containers();rows[0]['HostConfig']['CpuQuota']+=1
        with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
        rows[0]['HostConfig']['CpuQuota']-=1;runtime.containers()
        r.verify_config(config,budget);config['services']['evaluator']['memswap_limit']+=1
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(config,budget)
        config['services']['evaluator']['memswap_limit']-=1;r.verify_config(config,budget)
        bad=copy.deepcopy(source);bad['services']['bootstrap']={}
        with self.assertRaisesRegex(RuntimeError,'ALLOCATION_ROSTER_CHANGED'):r.overlay(bad,selected)
        selected['services']['bootstrap']={'millicpus':2000,'memoryBytes':1024**3}
        amended=r.plan(r.overlay(bad,selected));self.assertEqual(amended.record()['services']['bootstrap']['maximumConcurrent'],2)
        self.assertNotIn('aggregate', amended.record())
        selected['services']['postgres']['millicpus']=8000;selected['ceiling']['millicpus']=24000;r.selection(selected)

    def test_actual_prepare_records_explicit_workers_and_allocation(self):
        from test_edge_workers import EdgeWorkers
        import experiment_batch
        with tempfile.TemporaryDirectory() as folder,patch.object(experiment_batch,'global_lock_path',return_value=Path(folder)/'unit-heap.lock'),patch.object(r,'QUALIFICATION_NAME',allocation()):
            EdgeWorkers().test_actual_prepare_forwards_and_records_generated_workers()

    def test_invalid_missing_unbounded_and_ambiguous_allocations_refuse(self):
        for change in (lambda x:x['services']['evaluator'].pop('memoryBytes'),lambda x:x['driver'].update(millicpus=0),lambda x:x['services']['pgstream'].update(millicpus=True),lambda x:x['ceiling'].update(millicpus=0),lambda x:x['ceiling'].update(memoryBytes=10),lambda x:x['edge'].update(workerProcesses='auto'),lambda x:x['services'].update(unknown={'millicpus':1,'memoryBytes':1048576})):
            selected=allocation();change(selected)
            with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_RESOURCE_'):r.selection(selected)
        selected=allocation()
        with self.assertRaisesRegex(RuntimeError,'SELECTION_AMBIGUOUS'):a.selected_resources_profile(type('Args',(),{'diagnostic_resource_profile':r.QUALIFICATION_NAME,'diagnostic_resource_allocation':selected})())
        self.assertEqual(r.selection(allocation()),allocation())

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired controller path required')
    def test_actual_controller_worker_parser_receipt_and_host_controls(self):
        controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT']);remote=a.HERE.parent/'remote-pgstream';sys.path.insert(0,str(remote))
        import protocol
        selected=allocation();hosts={'sut':{'providerId':'synthetic-sut','cpuCores':8,'ramBytes':16*1024**3},'driver':{'providerId':'synthetic-driver','cpuCores':2,'ramBytes':4*1024**3}}
        names=('tools/mt-bench/m7-joined/stream_topology.py','tools/mt-bench/m7-joined/diagnostic_resources.py','tools/mt-bench/m7-joined/experiment_batch.py')
        deps={'version':1,'profile':'external-service-batch-v1','files':{name:'e'*64 for name in names}}
        spec={'reportMode':'discovery','pins':{'core':'a'*40,'deploy':'b'*40,'app':'sha256:'+'c'*64,'postgres':'sha256:'+'d'*64},'completionContract':'evaluator-work-v2','diagnostics':'on','tenants':2,'cadence':{'warmupSeconds':2,'idleSeconds':2,'loadSeconds':6,'accel':1,'hotFactor':1,'samplerIntervalSeconds':2,'probeEveryMs':1000,'socketsPerTenant':2,'offeredRps':7},'resourcePlan':{'hosts':hosts},'hosts':hosts,'pgstreamTopology':'external-service-v1','diagnosticResourceAllocation':selected,'helperDependencies':deps,'receipt':{'remotePgstreamTopology':'external-service-v1','remoteDiagnosticResourceAllocation':selected,'remoteHelperDependencies':deps}}
        script='import {topologyBinding} from '+json.dumps((controller/'tools/perf-cloud/pgstream-calibration.mjs').as_uri())+';let s="";for await(const c of process.stdin)s+=c;try{console.log(JSON.stringify(topologyBinding(JSON.parse(s))))}catch(e){console.error(e.message);process.exitCode=1}'
        def call(value):return subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(value),capture_output=True,text=True)
        actual=call(spec);self.assertEqual(actual.returncode,0,actual.stderr);self.assertEqual(json.loads(actual.stdout),{'pgstreamTopology':'external-service-v1','diagnosticResourceAllocation':selected})
        loader=importlib.util.spec_from_file_location('allocation_worker',controller/'tools/perf-cloud/pgstream-worker.py');worker=importlib.util.module_from_spec(loader);loader.loader.exec_module(worker)
        dependency={'root':'/synthetic/dependencies','receipt':'/synthetic/receipt','sha256':'e'*64}
        args=list(map(str,worker.prepare_arguments(spec,dependency)));start=args.index('--core-repo');parsed=a.parser().parse_args(['prepare','--directory','/tmp/synthetic-allocation',*args[start:]])
        self.assertIsNone(parsed.diagnostic_resource_profile);self.assertEqual(a.selected_resources_profile(parsed),selected)
        self.assertEqual(r.edge_worker_budget(a.selected_resources_profile(parsed))['workerProcesses'],1)
        protocol.allocation_boundary(selected,hosts)
        controls=((lambda x:x['receipt'].pop('remoteDiagnosticResourceAllocation'),'TOPOLOGY_RECEIPT',True),
                  # Multiple workers are now configurable; zero remains an
                  # invalid actor shape in both the controller and receiver.
                  (lambda x:x['diagnosticResourceAllocation']['edge'].update(workerProcesses=0),'ALLOCATION_SHAPE',False),
                  (lambda x:x['hosts']['sut'].update(cpuCores=1),'HOST_CAPACITY',False),
                  (lambda x:x.update(diagnosticResourceProfile=r.QUALIFICATION_NAME),'EXPLICIT_TOPOLOGY',True))
        for change,code,worker_gate in controls:
            with self.subTest(code=code):
                bad=copy.deepcopy(spec);change(bad);result=call(bad);self.assertNotEqual(result.returncode,0);self.assertIn(code,result.stderr)
                if worker_gate:
                    with self.assertRaises(RuntimeError):worker.prepare_arguments(bad,dependency)
                else:
                    # The worker builds argv; physical/edge admission is enforced
                    # by the actual caller and the receiving helper protocol.
                    with self.assertRaisesRegex(RuntimeError,'REMOTE_ALLOCATION_(EDGE|HOST_CAPACITY)'):
                        protocol.allocation_boundary(bad['diagnosticResourceAllocation'],bad['hosts'])
                self.assertEqual(call(spec).returncode,0)
                protocol.allocation_boundary(selected,hosts)

    def test_native_compose_render_preserves_explicit_limits(self):
        for selected in (allocation(),expanded_allocation()):
            with self.subTest(services=len(selected['services'])),tempfile.TemporaryDirectory() as directory:
                config=r.overlay({'services':{role:{'image':'synthetic.invalid/fixture@sha256:'+'a'*64}for role in selected['services']}},selected)
                file=Path(directory)/'compose.json';file.write_text(json.dumps(config))
                result=subprocess.run(['docker','compose','-f',str(file),'config','--format','json'],capture_output=True,text=True,timeout=10)
                if result.returncode and ('permission denied' in result.stderr.lower() or 'docker' in result.stderr.lower() and 'not found' in result.stderr.lower()):self.skipTest('native Compose unavailable: '+result.stderr[:120])
                self.assertEqual(result.returncode,0,result.stderr);rendered=json.loads(result.stdout)
                r.verify_config(rendered,r.plan(config))
                rendered['services']['nginx']['cpu_quota']+=1
                with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(rendered,r.plan(config))
                rendered['services']['nginx']['cpu_quota']-=1;r.verify_config(rendered,r.plan(config))

    def test_exact_quota_renderer_preserves_small_decimal_large_and_native_bounds(self):
        values=(1,9,10,65000,65001,128000,16777217000,1000000000000,r.MAX_DRIVER_MILLICPUS,r.MAX_ALLOCATION_MILLICPUS)
        for cpu in values:
            with self.subTest(millicpus=cpu),tempfile.TemporaryDirectory() as directory:
                selected=allocation();selected['services']['postgres']={'millicpus':cpu,'memoryBytes':r.NATIVE_INT64_MAX}
                selected['ceiling']={'millicpus':cpu+16000,'memoryBytes':r.NATIVE_INT64_MAX+32*1024**3}
                config=r.overlay({'services':{role:{'image':'synthetic.invalid/fixture'} for role in selected['services']}},selected)
                file=Path(directory)/'compose.json';file.write_text(json.dumps(config))
                actual=subprocess.run(['docker','compose','-f',str(file),'config','--format','json'],capture_output=True,text=True,timeout=10)
                self.assertEqual(actual.returncode,0,actual.stderr)
                rendered=json.loads(actual.stdout);r.verify_config(rendered,r.plan(config))
                service=rendered['services']['postgres'];quota,period=r.service_cpu_settings(cpu)
                self.assertNotIn('cpus',service)
                self.assertEqual((service['cpu_quota'],service['cpu_period']),(quota,period))
                self.assertEqual(quota*1000,cpu*period)
                self.assertGreaterEqual(quota,1000);self.assertLessEqual(quota,r.MAX_CFS_QUOTA_US)
                self.assertTrue(1000<=period<=1000000)
                self.assertEqual(service['mem_limit'],str(r.NATIVE_INT64_MAX))
                self.assertEqual(service['memswap_limit'],str(r.NATIVE_INT64_MAX))
                self.assertEqual(r.plan(config).record()['services']['postgres']['cpuEnforcement'],{'kind':'cfs-quota-period-v1','quotaMicros':quota,'periodMicros':period})

    def test_quota_native_census_rejects_alternate_missing_and_equivalent_changed_period(self):
        selected=allocation();selected['services']['postgres']['millicpus']=1
        config=r.overlay({'services':{role:{} for role in selected['services']}},selected)
        quota,period=r.service_cpu_settings(1)
        row={'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':'postgres'}},'HostConfig':{'NanoCpus':0,'CpuQuota':quota,'CpuPeriod':period,'Memory':selected['services']['postgres']['memoryBytes'],'MemorySwap':selected['services']['postgres']['memoryBytes']}}
        rows=[row];runtime=r.Runtime(config,r.plan(config).record(),lambda:rows)
        runtime.containers();original=copy.deepcopy(row['HostConfig'])
        controls=(lambda x:x.update(NanoCpus=1000000),lambda x:x.pop('CpuQuota'),lambda x:x.pop('CpuPeriod'),lambda x:x.update(CpuCount=1),lambda x:x.update(CpuQuota=quota//2,CpuPeriod=period//2))
        for change in controls:
            row['HostConfig']=copy.deepcopy(original);change(row['HostConfig'])
            with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
            row['HostConfig']=copy.deepcopy(original);runtime.containers()
        for key in ('cpu_count','cpu_percent','cpus'):
            bad=copy.deepcopy(config);bad['services']['postgres'][key]=1
            with self.assertRaisesRegex(RuntimeError,'ALTERNATE_LIMITS'):r.verify_config(bad,r.plan(config))
        bad=copy.deepcopy(selected);bad['services']['postgres']['millicpus']=r.MAX_ALLOCATION_MILLICPUS+1
        with self.assertRaisesRegex(RuntimeError,'CPU_INVALID:services.postgres.millicpus'):r.selection(bad)
        bad=copy.deepcopy(selected);bad['driver']['millicpus']=r.MAX_DRIVER_MILLICPUS+1
        with self.assertRaisesRegex(RuntimeError,'CPU_INVALID:driver.millicpus'):r.selection(bad)
        selected['services']['evaluator']['millicpus']=1
        self.assertEqual(r.verify_evaluator_cgroup(selected,'1000 1000000',str(selected['services']['evaluator']['memoryBytes']),'0')['millicpus'],1)
        with self.assertRaisesRegex(RuntimeError,'EFFECTIVE_CPU_PERIOD_CHANGED'):r.verify_evaluator_cgroup(selected,'500 500000',str(selected['services']['evaluator']['memoryBytes']),'0')
        r.verify_evaluator_cgroup(selected,'1000 1000000',str(selected['services']['evaluator']['memoryBytes']),'0')
        print('RED_RESTORED quota/period, alternate NanoCpus/CPU knobs, exact period, service and driver native bounds')

    def test_entered_legacy_explicit_cpu_config_and_record_keep_strict_native_path(self):
        selected=allocation();legacy={'services':{},r.PROFILE_KEY:selected}
        for role,limit in selected['services'].items():
            legacy['services'][role]={'cpus':limit['millicpus']/1000,'mem_limit':limit['memoryBytes'],'memswap_limit':limit['memoryBytes']}
        budget=r.plan(legacy);self.assertFalse(budget.cpu_enforcement);r.verify_config(legacy,budget)
        rows=[{'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':'postgres'}},'HostConfig':{'NanoCpus':selected['services']['postgres']['millicpus']*1000000,'Memory':selected['services']['postgres']['memoryBytes'],'MemorySwap':selected['services']['postgres']['memoryBytes']}}]
        runtime=r.Runtime(legacy,budget.record(),lambda:rows);runtime.containers()
        rows[0]['HostConfig']['NanoCpus']+=1
        with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
        rows[0]['HostConfig']['NanoCpus']-=1;runtime.containers()
        fresh=r.overlay({'services':{role:{} for role in selected['services']}},selected)
        with self.assertRaisesRegex(RuntimeError,'PLAN_CHANGED'):r.verify_config(fresh,budget)

if __name__=='__main__':unittest.main()


class FixtureDriverLocks(unittest.TestCase):
    def criterion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            from experiment_batch import global_lock_path
            with patch('experiment_batch.global_lock_path', return_value=root/'driver.lock'):
                first=r.Runtime(driver_scope=root/'first')
                same=r.Runtime(driver_scope=root/'first')
                independent=r.Runtime(driver_scope=root/'second')
                try:
                    first.acquire()
                    with self.assertRaisesRegex(RuntimeError,'OTHER_DRIVER_ACTIVE'): same.acquire()
                    independent.acquire()
                    first.close()
                    same.acquire()  # restored same-fixture entry after closure
                finally:
                    for runtime in (first,same,independent): runtime.close()

    def test_independent_fixtures_overlap_and_same_fixture_refuses_red_restored(self):
        self.criterion()
        with patch.object(r.fcntl,'flock',return_value=None):
            with self.assertRaises(AssertionError): self.criterion()
        self.criterion()
        print('FIXTURE_DRIVER_LOCK same-fixture overlap RED; independent fixtures GREEN; RESTORED_GREEN')
