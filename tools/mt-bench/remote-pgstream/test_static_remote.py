"""Narrow remote static K1/N1 plus honest native PENDING admission; no runtime claim."""
import copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import app,cell,protocol,producer,transport
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'m7-joined'))
import adapter as a,contract,run_configuration as rc,static_topology as st
from test_run_configuration import config as base_config,overlay as base_overlay
from test_static_topology import allocation as local_allocation
ROOT=Path(__file__).resolve().parents[3]

def selected():
    allocation=local_allocation();allocation['services']={k:v for k,v in allocation['services'].items()if not k.endswith('-2')}
    cfg=base_config();cfg['prepare'].pop('offered-rps',None);cfg['helperInstrument']=a.instrument()['sha256'];cfg['workSeconds']=3060;cfg['cleanupSeconds']=300
    cfg['prepare'].update({'core-commit':st.CORE,'deploy-commit':st.DEPLOY,'tenants':10,'replicas':1,'static-workers':1,'pgstream-topology':'external-service-v1','completion-contract':'evaluator-work-v2','diagnostic-resource-allocation':json.dumps(allocation),'generator-dependencies':'/synthetic/owned-dependencies','load-seconds':60,'warmup-seconds':10,'idle-seconds':30,'accel':1,'hot-factor':1,'sampler-interval':2,'probe-every-ms':30000,'sockets-per-tenant':1,'logical-polling-clients':1,'workload-mix':'realistic-v1','driver-shards':8})
    overlay=base_overlay();overlay['binding'].update(expiresAt=time.time()+3600,nativeSourceAdmission='diagnostic-build-v1',fixtureNetworks={'backend':'172.29.151.0/24','edge':'172.29.152.0/24'})
    deps=protocol.NATIVE_DEPENDENCIES|{'tools/mt-bench/m7-joined/'+n for n in('static_topology.py','role_instances.py','stream_topology.py','diagnostic_resources.py','experiment_batch.py','driver_shards.py','contract.py')}
    overlay['binding']['helperDependencies']={'version':1,'profile':protocol.NATIVE_PROFILE,'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in sorted(deps)}}
    overlay['hostInventory']={'sut':{'providerId':'100000000001','cpuCores':64,'ramBytes':128*1024**3},'driver':{'providerId':'100000000002','cpuCores':8,'ramBytes':16*1024**3}}
    projection=rc.remote_projection(cfg,overlay,{'status':'PENDING'});b=projection['binding']
    receipt={**projection['diagnosticReceiptTemplate'],**projection['remoteReceiptProjection'],'remoteFixtureNetworks':b['fixtureNetworks'],'status':'AUTHORIZED_DIAGNOSTIC'}
    hosts={r:{**h,'privateIPv4':b['appAddress']if r=='sut'else b['generatorAddress']}for r,h in b['workload']['resourcePlan']['hosts'].items()}
    spec={'profile':b['profile'],'reportMode':'discovery','runId':b['runId'],'cloudId':b['cloudId'],'nonce':b['nonce'],'tenants':b['tenants'],'logicalPollingClients':1,'pins':{**b['pair'],'app':b['imageId'],'postgres':transport.POSTGRES},'cadence':b['workload']['cadence'],**{k:b['workload'][k]for k in('primerConcurrency','jwtSetupConcurrency','resourcePlan')},'hosts':hosts,'port':b['port'],'expiresAt':b['expiresAt'],'k6Image':b['k6Image'],'extensionSha256':b['sourceSha256'],'transport':b['transport'],'completionContract':'evaluator-work-v2','diagnostics':projection['configuration']['diagnostics']['mode'],'receipt':receipt,'sourceQualification':{'path':'/synthetic/build-proof.json','sha256':'d'*64},**{k:b[k]for k in('pgstreamTopology','diagnosticResourceAllocation','helperDependencies','fixtureNetworks','staticTopology','nativeSourceAdmission')}}
    return cfg,overlay,projection,b,spec

class StaticRemote(unittest.TestCase):
    def test_exact_static_config_binding_allocation_and_pending_truth(self):
        cfg,overlay,projection,b,spec=selected();protocol.binding(b);protocol.topology_dependencies(b,ROOT)
        self.assertEqual(b['staticTopology'],{'kind':'static-hash-v1','workers':1});self.assertEqual(projection['receiptLimits']['staticWorkers'],1)
        self.assertEqual(spec['receipt']['sourceAcceptance'],{'status':'PENDING'});self.assertEqual(spec['receipt']['functionalAcceptanceAtAuthorization'],'PENDING')
        for mutate,code in((lambda x:x['staticTopology'].update(workers=2),'REMOTE_STATIC_K1_N1_ONLY'),(lambda x:x['diagnosticResourceAllocation']['services'].pop('socket-edge'),'REMOTE_STATIC_ALLOCATION'),(lambda x:x['helperDependencies']['files'].pop('tools/mt-bench/m7-joined/static_topology.py'),'DEPENDENCIES'),(lambda x:x.pop('staticTopology'),'REMOTE_TOPOLOGY_DEPENDENCIES'),(lambda x:x.update(nativeSourceAdmission='unknown'),'REMOTE_NATIVE_SOURCE_ADMISSION')):
            bad=copy.deepcopy(b);mutate(bad)
            with self.assertRaisesRegex(RuntimeError,code):protocol.binding(bad)
            protocol.binding(b)
        bad=copy.deepcopy(cfg);bad['prepare']['static-workers']=2
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_REMOTE_K1_N1_ONLY'):rc.remote_projection(bad,overlay,{'status':'PENDING'})
        bad=copy.deepcopy(cfg);bad['prepare']['replicas']=2
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_REMOTE_K1_N1_ONLY'):rc.remote_projection(bad,overlay,{'status':'PENDING'})

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired future controller required')
    def test_actual_controller_worker_cell_prepare_and_pending_receipt(self):
        controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT']);cfg,overlay,projection,b,spec=selected()
        script='import{runtimeBinding}from '+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+';let t="";for await(const c of process.stdin)t+=c;console.log(JSON.stringify(runtimeBinding(JSON.parse(t))));'
        result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(spec),text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stderr);actual=json.loads(result.stdout);self.assertEqual(actual,b)
        module=importlib.util.spec_from_file_location('static_future_worker',controller/'tools/perf-cloud/pgstream-worker.py');worker=importlib.util.module_from_spec(module);module.loader.exec_module(worker)
        with tempfile.TemporaryDirectory()as tmp:
            d=Path(tmp);(d/'input').mkdir();a.write(d/'input/binding.json',actual);a.write(d/'input/receipt.json',spec['receipt'])
            with patch.object(worker,'ROOT',d):argv=list(map(str,worker.prepare_arguments(spec,{'root':'/synthetic/deps','receipt':'/synthetic/provenance','sha256':'e'*64})))[2:]
            def enter(args=argv):
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(a,'prepare')as prepare,patch.object(app,'record_prepared_binding'):
                    cell.main();return prepare.call_args.args[0]
            parsed=enter();self.assertEqual(parsed.static_workers,1);self.assertEqual(parsed.replicas,1)
            self.assertEqual(rc.from_args(parsed,a.instrument()['sha256']),projection['configuration'])
            manifest={**projection['configuration'],'instrument':{'sha256':a.instrument()['sha256']},'runConfiguration':projection['configuration'],'diagnosticResources':{'profile':projection['configuration']['resources']['profile']}}
            self.assertEqual(contract.receipt_scope(manifest,spec['receipt'],'deploy')['functionalAcceptance'],'PENDING')
            i=argv.index('--static-workers');missing=argv[:i]+argv[i+2:]
            with self.assertRaisesRegex(RuntimeError,'REMOTE_STATIC_PREPARE_MIRROR'):enter(missing)
            for change,code in((lambda r:r.pop('remoteStaticTopology'),'REMOTE_STATIC_PREPARE_MIRROR'),(lambda r:r['limits'].update(staticWorkers=2),'REMOTE_STATIC_RECEIPT'),(lambda r:r.update(functionalAcceptanceAtAuthorization='PASS'),'REMOTE_NATIVE_PREPARE_AUTHORIZATION'),(lambda r:r['sourceAcceptance'].update(reference='/synthetic/false-pass'),'REMOTE_NATIVE_PENDING_TRUTH'),(lambda r:r.pop('remoteNativeSourceAdmission'),'REMOTE_NATIVE_SOURCE_ADMISSION_RECEIPT')):
                bad=copy.deepcopy(spec['receipt']);change(bad);a.write(d/'input/receipt.json',bad)
                with self.assertRaisesRegex(RuntimeError,code):enter()
                a.write(d/'input/receipt.json',spec['receipt']);enter()

    def test_actual_static_stage_contract_includes_edge_and_omits_retired_pool_init(self):
        from test_role_instances import config as roles
        c=roles(k=1,apis=1)
        for name,s in c['services'].items():
            if name!='api':s['restart']='unless-stopped'
        c['services']['socket-edge']={'command':st.EDGE_COMMAND,'restart':'unless-stopped','environment':{'NS_REALTIME_STATIC_COUNT':'1','NS_REALTIME_STATIC_ROUTE_MAP':json.dumps({'version':1,'rule':'sha256-modulo-v1','count':1,'upstreams':['http://realtime:1339/']})}}
        c['services']['pgstream']={'command':a.stream_topology.EXTERNAL_COMMAND}
        m={'pair':{'core':st.CORE,'deploy':st.DEPLOY},'profile':'pgstream-sample','runPurpose':'discovery','pgstreamTopology':'external-service-v1','completionContract':'evaluator-work-v2','replicas':1,'staticTopology':{'kind':st.KIND,'workers':1}}
        plan=producer.deployment_plan(c,True,1,static_manifest=m);self.assertNotIn('pool-initialize',[r[0]for r in plan]);launch=next(r[2]for r in plan if r[0]=='remaining-roles')
        for role in('evaluator','realtime','pgstream','socket-edge'):self.assertIn(role,launch)
        self.assertNotIn('placement-operator',launch)
        bad=copy.deepcopy(c);bad['services']['socket-edge']['command']=['node','other.js']
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_EDGE_COMMAND'):producer.deployment_plan(bad,True,1,static_manifest=m)
        with self.assertRaisesRegex(RuntimeError,'REMOTE_STATIC_SELECTION_REQUIRED'):producer.deployment_plan(c,True,1)
        producer.deployment_plan(c,True,1,static_manifest=m)

if __name__=='__main__':unittest.main()
