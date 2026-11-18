"""Explicit allocation through canonical quotas and real controller/worker/parser."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
import diagnostic_resources as r

ROLES=('postgres','vault','admin','primer','api','realtime','evaluator','tenant-admin','ui','nginx','pgstream')

def allocation():
    return {'version':1,'services':{role:{'millicpus':r.role_limit(role,r.QUALIFICATION_NAME).cpu,'memoryBytes':r.role_limit(role,r.QUALIFICATION_NAME).memory} for role in ROLES},'driver':{'millicpus':2000,'memoryBytes':4*1024**3},'ceiling':{'millicpus':16000,'memoryBytes':32*1024**3},'edge':{'workerProcesses':1,'workerConnections':16384}}

class ExplicitAllocation(unittest.TestCase):
    def test_authored_allocation_replaces_reference_but_readback_still_refuses(self):
        selected=allocation();selected['services']['api']={'millicpus':3000,'memoryBytes':4*1024**3}
        source={'services':{role:{} for role in ROLES}}
        source['services']['api'].update(cpus=.25,mem_limit=512*1024**2,memswap_limit=512*1024**2)
        original=copy.deepcopy(source)
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):
            r.overlay(source,r.QUALIFICATION_NAME)
        applied=r.overlay(source,selected)
        self.assertEqual(source,original)
        self.assertEqual(applied['services']['api']['cpus'],3)
        self.assertEqual(applied['services']['api']['mem_limit'],4*1024**3)
        self.assertEqual(applied['services']['api']['memswap_limit'],4*1024**3)
        budget=r.plan(applied);r.verify_config(applied,budget)
        broken=copy.deepcopy(applied);broken['services']['api']['cpus']=.5
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(broken,budget)
        r.verify_config(applied,budget)
        print('RED_RESTORED reference conflict; explicit allocation replaces; changed actual limit refuses')

    def test_exact_roster_overlap_and_driver_native_quota_controls(self):
        selected=allocation();source={'services':{role:{} for role in ROLES}};config=r.overlay(source,selected);budget=r.plan(config)
        self.assertEqual(source,{'services':{role:{} for role in ROLES}})
        self.assertEqual(budget.record()['aggregate']['millicpus'],6500)
        self.assertEqual(budget.record()['standalone']['k6']['millicpus'],2000)
        self.assertEqual(r.edge_worker_budget(selected),{'workerProcesses':1,'workerConnections':16384,'nginxMillicpus':125,'source':'explicit-resource-allocation-v1'})
        rows=[{'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':role}},'HostConfig':{'NanoCpus':selected['services'][role]['millicpus']*1000000,'Memory':selected['services'][role]['memoryBytes'],'MemorySwap':selected['services'][role]['memoryBytes']}} for role in ROLES]
        runtime=r.Runtime(config,budget.record(),lambda:rows)
        runtime.containers();rows[0]['HostConfig']['NanoCpus']=0
        with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
        rows[0]['HostConfig']['NanoCpus']=selected['services']['postgres']['millicpus']*1000000;runtime.containers()
        r.verify_config(config,budget);config['services']['evaluator']['memswap_limit']+=1
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(config,budget)
        config['services']['evaluator']['memswap_limit']-=1;r.verify_config(config,budget)
        bad=copy.deepcopy(source);bad['services']['bootstrap']={}
        with self.assertRaisesRegex(RuntimeError,'ALLOCATION_ROSTER_CHANGED'):r.overlay(bad,selected)
        selected['services']['bootstrap']={'millicpus':2000,'memoryBytes':1024**3}
        amended=r.plan(r.overlay(bad,selected));self.assertEqual(amended.record()['services']['bootstrap']['maximumConcurrent'],2)
        self.assertEqual(amended.record()['aggregate']['millicpus'],10500)
        selected['services']['postgres']['millicpus']=8000;selected['ceiling']['millicpus']=24000;r.selection(selected)

    def test_actual_prepare_records_explicit_workers_and_allocation(self):
        from test_edge_workers import EdgeWorkers
        import experiment_batch
        with tempfile.TemporaryDirectory() as folder,patch.object(experiment_batch,'global_lock_path',return_value=Path(folder)/'unit-heap.lock'),patch.object(r,'QUALIFICATION_NAME',allocation()):
            EdgeWorkers().test_actual_prepare_forwards_and_records_generated_workers()

    def test_invalid_missing_unbounded_and_ambiguous_allocations_refuse(self):
        for change in (lambda x:x['services']['evaluator'].pop('memoryBytes'),lambda x:x['driver'].update(millicpus=0),lambda x:x['services']['pgstream'].update(millicpus=True),lambda x:x['ceiling'].update(millicpus=1000),lambda x:x['ceiling'].update(memoryBytes=10),lambda x:x['edge'].update(workerProcesses='auto'),lambda x:x['services'].update(unknown={'millicpus':1,'memoryBytes':1048576})):
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
                  (lambda x:x['diagnosticResourceAllocation']['edge'].update(workerProcesses=2),'ALLOCATION_SHAPE',False),
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
        selected=allocation();config=r.overlay({'services':{role:{'image':'synthetic.invalid/fixture@sha256:'+'a'*64}for role in ROLES}},selected)
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'compose.json';file.write_text(json.dumps(config))
            result=subprocess.run(['docker','compose','-f',str(file),'config','--format','json'],capture_output=True,text=True,timeout=10)
            if result.returncode and ('permission denied' in result.stderr.lower() or 'docker' in result.stderr.lower() and 'not found' in result.stderr.lower()):self.skipTest('native Compose unavailable: '+result.stderr[:120])
            self.assertEqual(result.returncode,0,result.stderr);rendered=json.loads(result.stdout)
            r.verify_config(rendered,r.plan(config))
            rendered['services']['nginx']['cpus']=0
            with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(rendered,r.plan(config))
            rendered['services']['nginx']['cpus']=.125;r.verify_config(rendered,r.plan(config))

if __name__=='__main__':unittest.main()
