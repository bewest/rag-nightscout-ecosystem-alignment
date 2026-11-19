"""Source-only startup mirrors, actual paired CLI/cell and PostgreSQL readback controls."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import copy,importlib.util,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import app,cell,protocol,producer
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'m7-joined'))
import adapter as a,commissioning_wal as w,run_configuration as rc
from test_static_remote import selected


def startup(tenants=1000):
    cfg,overlay,_,_,spec=selected();cfg['prepare'].update({'commissioning-slot-wal-mib':1024,'tenant-readiness':'serve','primer-concurrency':16,'tenants':tenants,'logical-polling-clients':tenants//10,'load-seconds':1800});cfg['workSeconds']=4860
    allocation=json.loads(cfg['prepare']['diagnostic-resource-allocation'])
    for role in ('admin','primer'):allocation['services'][role]['millicpus']=1000
    cfg['prepare']['diagnostic-resource-allocation']=json.dumps(allocation);overlay['binding']['expiresAt']=time.time()+5400
    result=rc.remote_projection(cfg,overlay,{'status':'PENDING'});b=result['binding'];receipt={**result['diagnosticReceiptTemplate'],**result['remoteReceiptProjection'],'remoteFixtureNetworks':b['fixtureNetworks'],'status':'AUTHORIZED_DIAGNOSTIC'}
    spec.update(tenants=tenants,logicalPollingClients=tenants//10,expiresAt=b['expiresAt'],receipt=receipt,**b['workload'],**{key:b[key]for key in('commissioningSlotWalMiB','tenantReadiness','helperDependencies','diagnosticResourceAllocation')})
    return cfg,overlay,result,b,spec


class StartupRemote(unittest.TestCase):
    def test_projection_exact_scope_cpu_fields_and_dependency_red_restore(self):
        for tenants in (1000,10000):
            cfg,overlay,result,b,spec=startup(tenants);protocol.binding(b);protocol.topology_dependencies(b,Path(__file__).resolve().parents[3]);self.assertEqual(b['commissioningSlotWalMiB'],1024);self.assertEqual(b['tenantReadiness'],'serve');self.assertEqual(b['workload']['cadence']['loadSeconds'],1800);self.assertEqual(b['workload']['cadence']['driverShards'],8)
            for mutate,code in ((lambda x:x.update(commissioningSlotWalMiB=256),'REMOTE_STARTUP_SELECTION'),(lambda x:x.update(commissioningSlotWalMiB=True),'REMOTE_STARTUP_SELECTION'),(lambda x:x.pop('tenantReadiness'),'REMOTE_STARTUP_SELECTION'),(lambda x:x['diagnosticResourceAllocation']['services']['admin'].update(millicpus=250),'REMOTE_STARTUP_ADMIN_PRIMER_CPU'),(lambda x:x['diagnosticResourceAllocation']['services']['primer'].update(millicpus=500),'REMOTE_STARTUP_ADMIN_PRIMER_CPU'),(lambda x:x['helperDependencies']['files'].pop('tools/mt-bench/m7-joined/commissioning_wal.py'),'DEPENDENCIES')):
                bad=copy.deepcopy(b);mutate(bad)
                with self.assertRaisesRegex(RuntimeError,code):protocol.binding(bad)
                protocol.binding(b)
            overlay['binding']['commissioningSlotWalMiB']=1024
            with self.assertRaisesRegex(RuntimeError,'MIRROR_REFUSED'):rc.remote_projection(cfg,overlay,{'status':'PENDING'})

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired new controller required')
    def test_actual_paired_controller_worker_cell_and_receipt_digest(self):
        controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT']);cfg,overlay,result,b,spec=startup();program='import{runtimeBinding}from '+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+';let t="";for await(const c of process.stdin)t+=c;console.log(JSON.stringify(runtimeBinding(JSON.parse(t))));'
        actual=subprocess.run(['node','--input-type=module','-e',program],input=json.dumps(spec),text=True,capture_output=True);self.assertEqual(actual.returncode,0,actual.stderr);self.assertEqual(json.loads(actual.stdout),b)
        module=importlib.util.spec_from_file_location('startup_worker',controller/'tools/perf-cloud/pgstream-worker.py');worker=importlib.util.module_from_spec(module);module.loader.exec_module(worker)
        with tempfile.TemporaryDirectory()as tmp:
            d=Path(tmp);(d/'input').mkdir();a.write(d/'input/binding.json',b);a.write(d/'input/receipt.json',spec['receipt'])
            with patch.object(worker,'ROOT',d):argv=list(map(str,worker.prepare_arguments(spec,{'root':'/synthetic/deps','receipt':'/synthetic/deps.json','sha256':'e'*64})))[2:]
            def enter(args=argv):
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(a,'prepare')as prepare,patch.object(app,'record_prepared_binding'):
                    cell.main();return prepare.call_args.args[0]
            prep=enter();self.assertEqual(prep.commissioning_slot_wal_mib,1024);self.assertEqual(prep.tenant_readiness,'serve');self.assertEqual(prep.primer_concurrency,16);self.assertEqual(rc.from_args(prep,a.instrument()['sha256']),result['configuration'])
            for flag in ('--commissioning-slot-wal-mib','--tenant-readiness'):
                i=argv.index(flag)
                with self.assertRaisesRegex(RuntimeError,'STARTUP_PREPARE_MIRROR'):enter(argv[:i]+argv[i+2:])
            for key,value in (('remoteCommissioningSlotWalMiB',256),('remoteTenantReadiness','all')):
                bad=copy.deepcopy(spec['receipt']);bad[key]=value;a.write(d/'input/receipt.json',bad)
                with self.assertRaisesRegex(RuntimeError,'STARTUP_PREPARE_MIRROR'):enter()
                a.write(d/'input/receipt.json',spec['receipt']);enter()
            bad=copy.deepcopy(spec);bad['receipt']['remoteCommissioningSlotWalMiB']=256
            with self.assertRaisesRegex(RuntimeError,'PGCAL_STARTUP_RECEIPT'):worker.prepare_arguments(bad,{'root':'/synthetic/deps','receipt':'/synthetic/deps.json','sha256':'e'*64})

    def test_actual_setting_reader_wrong_missing_unit_pending_and_restore(self):
        cfg,overlay,result,b,spec=startup();m={**result['configuration'],'pair':b['pair'],'imageId':b['imageId']}
        with tempfile.TemporaryDirectory()as tmp:
            d=Path(tmp)
            for raw in ('max_slot_wal_keep_size\t1024\tMB\tf\n','max_slot_wal_keep_size\t256\tMB\tf\n','','max_slot_wal_keep_size\t1024\tkB\tf\n','max_slot_wal_keep_size\t1024\tMB\tt\n','max_slot_wal_keep_size\t1024\tMB\tf\n'*2,'max_slot_wal_keep_size\t1024\tMB\tf\n'):
                with patch.object(a,'psql',return_value=raw)as query:
                    if raw=='max_slot_wal_keep_size\t1024\tMB\tf\n':self.assertEqual(w.runtime(a,d,m,'control')['status'],'PASS')
                    else:
                        with self.assertRaisesRegex(RuntimeError,'SLOT_WAL_RUNTIME'):w.runtime(a,d,m,'control')
                    self.assertIn('pg_settings',query.call_args.args[1])
            self.assertEqual(a.document(d/'commissioning-wal-control.json')['commissioningSlotWalMiB'],1024)

    def test_source_witness_hashes_exact_git_bytes_and_refuses_changed_baseline(self):
        import hashlib
        m={'commissioningSlotWalMiB':1024,'tenantReadiness':'serve','profile':'pgstream-sample','runPurpose':'discovery','pair':{'core':'a'*40,'deploy':'b'*40}}
        def read(argv,**kwargs):
            self.assertTrue(kwargs['binary'])
            return b'max_slot_wal_keep_size=256MB\n' if str(argv[-1]).endswith('compose.yaml') else b'exact source file\n'
        with patch.object(a,'command',side_effect=read):
            witness=w.verify_source(a,m,'/synthetic/core','/synthetic/deploy');self.assertEqual(witness['files'][w.SOURCE_FILES[0]],hashlib.sha256(b'exact source file\n').hexdigest())
        with patch.object(a,'command',return_value=b'max_slot_wal_keep_size=128MB\n'):
            with self.assertRaisesRegex(RuntimeError,'BASELINE_CHANGED'):w.verify_source(a,m,'/synthetic/core','/synthetic/deploy')
        with patch.object(a,'command',side_effect=read):w.verify_source(a,m,'/synthetic/core','/synthetic/deploy')

    def test_actual_stage_plan_retains_admin_verification_before_apis(self):
        from test_role_instances import config as roles
        import static_topology as st
        c=roles(k=1,apis=1)
        c['services']['socket-edge']={'command':st.EDGE_COMMAND,'environment':{'NS_REALTIME_STATIC_COUNT':'1','NS_REALTIME_STATIC_ROUTE_MAP':json.dumps({'version':1,'rule':'sha256-modulo-v1','count':1,'upstreams':['http://realtime:1339/']})}}
        c['services']['pgstream']={'command':a.stream_topology.EXTERNAL_COMMAND}
        for spec in c['services'].values():spec['restart']='unless-stopped'
        m={'pair':{'core':st.CORE,'deploy':st.DEPLOY},'profile':'pgstream-sample','runPurpose':'discovery','pgstreamTopology':'external-service-v1','completionContract':'evaluator-work-v2','replicas':1,'staticTopology':{'kind':st.KIND,'workers':1}}
        names=[row[0]for row in producer.deployment_plan(c,True,16,static_manifest=m,platform_verification=True)]
        self.assertLess(names.index('commission'),names.index('platform-verify'));self.assertLess(names.index('platform-verify'),names.index('apis'));self.assertNotIn('pool-initialize',names)
        del c['services']['socket-edge']
        startup_names=[row[0]for row in producer.deployment_plan(c,True,16,platform_verification=True)]
        self.assertNotIn('pool-initialize',startup_names);self.assertLess(startup_names.index('platform-verify'),startup_names.index('apis'))

if __name__=='__main__':unittest.main()
