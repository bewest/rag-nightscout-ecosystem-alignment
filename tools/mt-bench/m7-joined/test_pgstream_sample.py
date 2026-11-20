"""Offline sample instrumentation checks. No Docker, database or workload."""
import copy
import contextlib
import tempfile
from pathlib import Path
import unittest
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
import adapter as a
import sql_attribution as sql
from contract import CADENCE

class Sample(unittest.TestCase):
    def test_named_runtime_fixture_and_orphan_resource_control(self):
        args=SimpleNamespace(tenants=2,replicas=1,fixture_project=None)
        self.assertEqual(a.fixture_project(args,'a'*32),'nsm7-aaaaaaaaaaaa-n2-a1')
        args.fixture_project='ns-rest-joined-baseline'
        self.assertEqual(a.fixture_project(args,'a'*32),args.fixture_project)
        for name in ('../peer','UPPER','', 'x'*64):
            args.fixture_project=name
            with self.assertRaisesRegex(RuntimeError,'FIXTURE_PROJECT_INVALID'):a.fixture_project(args,'a'*32)
        names={'network':'peer_default\n','volume':'peer_data\n'}
        with patch.object(a,'command',side_effect=lambda argv:names[argv[1]]):
            a.unused_project_namespace('ns-rest-joined-baseline')
            for kind in names:
                original=names[kind];names[kind]+='ns-rest-joined-baseline_private\n'
                with self.assertRaisesRegex(RuntimeError,'PROJECT_NAMESPACE_EXISTS'):a.unused_project_namespace('ns-rest-joined-baseline')
                names[kind]=original
                a.unused_project_namespace('ns-rest-joined-baseline')
        with self.assertRaisesRegex(RuntimeError,'ATTACH_USE_EXISTING_PROJECT'):
            a.attach(SimpleNamespace(fixture_project='ns-rest-joined-baseline'))

    def test_prepare_existing_images_exact_pair_break_restore(self):
        args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',core_commit='a'*40,deploy_commit='b'*40,
                             image='sha256:'+'c'*64,image_id=None,postgres_image='sha256:'+'d'*64)
        app={'Id':args.image,'Config':{'Labels':{'org.opencontainers.image.revision':args.core_commit,
                                                        'org.nightscout.deploy.revision':args.deploy_commit}}}
        postgres={'Id':args.postgres_image}
        def inspect(argv,**kwargs):return json.dumps([app if argv[-1]==args.image else postgres])
        with patch.object(a,'command',side_effect=inspect):
            self.assertEqual(a.prepare_image_inputs(args)['appImageId'],args.image)
            app['Config']['Labels']['org.opencontainers.image.revision']='e'*40
            with self.assertRaisesRegex(RuntimeError,'IMAGE_CORE_MISMATCH'):a.prepare_image_inputs(args)
            app['Config']['Labels']['org.opencontainers.image.revision']=args.core_commit
            self.assertEqual(a.prepare_image_inputs(args)['appImageId'],args.image)
            app['Config']['Labels']['org.nightscout.deploy.revision']='e'*40
            with self.assertRaisesRegex(RuntimeError,'IMAGE_DEPLOY_MISMATCH'):a.prepare_image_inputs(args)
            app['Config']['Labels']['org.nightscout.deploy.revision']=args.deploy_commit
            app['Id']='sha256:'+'e'*64
            with self.assertRaisesRegex(RuntimeError,'IMAGE_ID_CHANGED'):a.prepare_image_inputs(args)
            app['Id']=args.image;postgres['Id']='sha256:'+'e'*64
            with self.assertRaisesRegex(RuntimeError,'POSTGRES_IMAGE_CHANGED'):a.prepare_image_inputs(args)
            postgres['Id']=args.postgres_image
            self.assertEqual(a.prepare_image_inputs(args)['postgresImageId'],args.postgres_image)
        args.profile='fresh-image-diagnostic'
        with patch.object(a,'command') as command:
            self.assertIsNone(a.prepare_image_inputs(args));command.assert_not_called()

    def diagnostic(self):
        from profile_provenance import selection
        m={'profile':'pgstream-sample','runPurpose':'discovery','pair':{'core':'a'*40,'deploy':'b'*40},'instrument':{'sha256':'c'*64},'imageId':'sha256:'+'d'*64,'tenants':2,'replicas':1,'diagnostics':selection(),'cadence':dict(CADENCE['pgstream-sample'])}
        receipt={'kind':'joined-diagnostic','status':'AUTHORIZED_DIAGNOSTIC','functionalAcceptanceAtAuthorization':'PENDING','pair':m['pair'],'instrument':'c'*64,'imageId':m['imageId'],'limits':{'tenants':2,'apiReplicas':1,'trafficSeconds':600}}
        return m,receipt
    def test_pending_discovery_receipt_exact_identity_and_accepted_mode_unchanged(self):
        from contract import receipt_scope,campaign_check,pilot_check
        m,r=self.diagnostic()
        for operation in ('build','deploy','run'):
            self.assertEqual(receipt_scope(m,r,operation)['functionalAcceptance'],'UNACCEPTED')
        for change in ({'pair':{'core':'f'*40,'deploy':'b'*40}},{'imageId':'sha256:'+'e'*64},{'instrument':'0'*64},{'status':'PASS'},{'functionalAcceptanceAtAuthorization':'PASS'}):
            with self.assertRaises(RuntimeError):receipt_scope(m,{**r,**change},'run')
        with self.assertRaisesRegex(RuntimeError,'FROZEN_ACCEPTANCE_REQUIRED'):receipt_scope({**m,'runPurpose':'acceptance'},r,'run')
        self.assertEqual(receipt_scope({**m,'runPurpose':'acceptance'},{'kind':'joined-acceptance','status':'PASS','pair':m['pair'],'evidenceSha256':'e'*64},'run')['kind'],'accepted-capacity')
        for check in (campaign_check,pilot_check):
            with self.assertRaisesRegex(RuntimeError,'NOT_ACCEPTANCE'):check({**m,'functionalAcceptance':'UNACCEPTED','capacityAcceptance':'NOT_GRANTED'})
    def test_selected_knobs_count_scope_and_ordinary_command(self):
        import discovery
        m,r=self.diagnostic();m['tenants']=100;r['limits']['tenants']=100
        self.assertEqual(a.receipt_scope(m,r,'run')['kind'],'diagnostic-discovery')
        args=SimpleNamespace(profile='pgstream-sample',warmup_seconds=5,idle_seconds=10,load_seconds=20,accel=1,hot_factor=1,sampler_interval=1)
        knobs=a.cadence_options(args);self.assertEqual((knobs['loadSeconds'],knobs['hotFactor'],knobs['samplerIntervalSeconds']),(20,1,1))
        m.update(cadence=knobs,owner='e'*32,project='synthetic',port=1234,settingsFingerprint={'sha256':'f'*64})
        r['limits']['trafficSeconds']=20;a.receipt_scope(m,r,'run')
        cmd=discovery.k6_command(a,Path('/synthetic'),m,'sha256:synthetic','synthetic-run')
        self.assertIn('HOT_FACTOR=1',cmd);self.assertIn('ACCEL=1',cmd);self.assertIn('DURATION=20',cmd)
        with self.assertRaisesRegex(RuntimeError,'KNOB_PROFILE'):a.cadence_options(SimpleNamespace(profile='capacity',load_seconds=20))
    def test_discovery_pipeline_keeps_pending_scope_and_sample_proofs(self):
        import discovery
        from test_contract import PROFILE
        m,_=self.diagnostic();m.update(owner='e'*32,hostIdentity='f'*64,generator={},profileSelection=PROFILE)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'deploy-before-host.json').write_text('{}')
            def load(a,d,m,image,record):
                rows=[{'tenant':str(i),'stored':1,'match':True,'probeAccepted':1,'probeStored':1,'probeUncertain':0,'probeRefused':0,'probePending':0} for i in range(2)]
                # Control eligibility now requires the full exact count-observer metadata.
                record.value.update(probe={'completedOutput':{'verdict':'PASS'}},oracle={'verdict':'GREEN','failureCount':0,'failures':[],'missingFieldCount':0,'accepted':2,'stored':2,'uncertain':0,'domains':{'entries':2,'devicestatus':0,'treatments':0},'rows':rows,'probeCountProof':'KNOWN','probeAccounting':{'version':2,'admissionsClosed':True,'pending':0}},processes={'k6':{'returncode':0},'probe':{'returncode':0}},settingsFingerprintObservation={'verdict':'PASS'});record.save()
            with contextlib.ExitStack() as stack:
                for name in ('frozen','quiet','verify','image','verify_generator','readiness','psql','phase_snapshot','k6_tenants'):stack.enter_context(patch.object(a,name))
                stack.enter_context(patch.object(a.time,'sleep'));stack.enter_context(patch.object(a,'command',return_value='[{"Id":"sha256:synthetic"}]'))
                stack.enter_context(patch.object(a,'sample_preflight',return_value=({},{})))
                proof=stack.enter_context(patch.object(a,'sample_results',return_value={'idle':{'status':'MEASURED'}}))
                stack.enter_context(patch.object(a,'control',side_effect=lambda *_:a.write(d/'load/oracle-control.json',{'baseline':'GREEN','broken':'RED','restored':'GREEN'})))
                stack.enter_context(patch.object(discovery,'discovery_load',side_effect=load));stack.enter_context(patch('reduce.measurements',return_value={'complete':True}))
                result=discovery.run_discovery(a,d,m,'sha256:synthetic')
                proof.assert_called_once();self.assertEqual(result['status'],'MEASURED');self.assertEqual(result['functionalAcceptance'],'UNACCEPTED');self.assertEqual(result['capacityAcceptance'],'NOT_GRANTED');self.assertNotIn('verdict',result)
    def test_setup_failure_preserves_deployment_and_new_success_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'deployment.json').write_text('retained');m={'owner':'a'*32,'project':'synthetic','cadence':{'samplerIntervalSeconds':1}}
            # This test isolates setup retry retention; real companion-format admission
            # is exercised in test_collection_segments against actual files.
            with patch.object(a.collection_segments,'preflight',return_value={'status':'CHECKED'}),patch.object(a,'sample_context',return_value=({},{})),patch.object(a,'phase_snapshot',side_effect=RuntimeError('M7_SQL_SETUP')):
                with self.assertRaisesRegex(RuntimeError,'SQL_SETUP'):a.sample_preflight(d,m,'sha256:synthetic')
            failed=next((d/'setup-attempts').iterdir());self.assertEqual(a.document(failed/'setup.json')['status'],'FAILED')
            def snapshot(_,out,name):
                a.write(out/(name+'-cgroups.json'),{'roles':{'evaluator':{'hostProcesses':{'1':{'name':'node'},'2':{'name':'pgstream'}}}}});(out/(name+'-pg-statements.tsv')).write_text('')
            @contextlib.contextmanager
            def sampler(_,out):
                (out/'docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n1\tsynthetic-evaluator-1\t0%\t1MiB / 2MiB\n');yield
            with patch.object(a.collection_segments,'preflight',return_value={'status':'CHECKED'}),patch.object(a,'sample_context',return_value=({},{})),patch.object(a,'phase_snapshot',side_effect=snapshot),patch.object(a,'sampling',sampler),patch.object(a,'command',return_value='k6 synthetic --summary-export'),patch.object(a.time,'sleep'):
                a.sample_preflight(d,m,'sha256:synthetic')
            self.assertEqual(len(list((d/'setup-attempts').iterdir())),2)
            self.assertEqual(a.document(failed/'setup.json')['status'],'FAILED');self.assertEqual((d/'deployment.json').read_text(),'retained')
            self.assertFalse((d/'load').exists());self.assertFalse((d/'idle').exists())
    def test_attached_fixture_identity_refuses_restart_and_cleanup_leaves_runtime(self):
        row={'Id':'a'*64,'Image':'sha256:'+'b'*64,'State':{'StartedAt':'synthetic-birth'},'Config':{'Labels':{'com.docker.compose.project':'synthetic','com.docker.compose.service':'evaluator'}}}
        m={'attached':True,'project':'synthetic','owner':'c'*32,'attachedResources':{row['Id']:a.attached_identity(row)}}
        with patch.object(a,'resources',return_value=[row]):a.assert_owned(m)
        changed=copy.deepcopy(row);changed['State']['StartedAt']='new-birth'
        with patch.object(a,'resources',return_value=[changed]):
            with self.assertRaisesRegex(RuntimeError,'ATTACHED_RESOURCE_CHANGED'):a.assert_owned(m)
        with tempfile.TemporaryDirectory() as temp,patch.object(a,'assert_owned'),patch.object(a,'compose') as runtime:
            a.down(Path(temp),m);runtime.assert_not_called()
        with patch.object(a,'resources',return_value=[row]):a.assert_owned(m)
    def test_shared_host_diagnostic_records_contention_without_accepted_claim(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(a,'fixture_inventory',return_value={'load':[99],'containers':[{'owned':False}]}):
            m={'profile':'pgstream-sample','runPurpose':'discovery'};a.quiet(Path(temp),m,'setup')
            self.assertIn('no capacity acceptance',a.document(Path(temp)/'setup-host.json')['scope'])
            with self.assertRaisesRegex(RuntimeError,'FOREIGN_ACTIVE'):a.quiet(Path(temp),{**m,'runPurpose':'acceptance'},'accepted')
    def test_fixed_ordinary_sample_and_separate_witness_no_restart(self):
        sample=CADENCE['pgstream-sample']
        self.assertEqual((sample['accel'],sample['hotFactor'],sample['probeEveryMs'],sample['restart']),(1,1,300000,False))
        self.assertGreaterEqual(sample['loadSeconds'],300)
    def test_generated_probe_positive_and_completion_client_red_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            from probe import generate
            target=Path(temp)/'probe.cjs';generate(a.ROOT,target)
            subprocess.run(['node',str(a.HERE/'sample-probe-control.cjs'),str(target)],check=True,capture_output=True,timeout=10)
    def test_pgstream_deployment_omits_retired_legacy_reader_and_control_restores_it(self):
        config={'services':{name:{'command':['node','entrypoint.js',name]} for name in ('api','realtime','evaluator','tenant-admin')}}
        legacy=a.deployment_plan(config)
        self.assertIn('feed-reader',next(args for name,scope,args in legacy if name=='admin-feed'))
        selected=a.deployment_plan(config,pgstream=True)
        self.assertNotIn('feed-reader',[arg for name,scope,args in selected for arg in args])
        self.assertIn('admin',next(args for name,scope,args in selected if name=='admin-feed'))
        self.assertEqual([row[0] for row in legacy],[row[0] for row in selected])
        self.assertIn('feed-reader',next(args for name,scope,args in a.deployment_plan(config) if name=='admin-feed'))
    def test_runtime_roster_does_not_require_or_credit_retired_reader(self):
        import profile_provenance as profile
        chosen=profile.selection();env=[key+'='+value for key,value in chosen['environment'].items()]
        admin={'Config':{'Labels':{'com.docker.compose.service':'admin'},'Env':env},'State':{'Running':True}}
        config={'services':{'admin':{},'feed-reader':{}}}
        profile.runtime_environment([admin],chosen,config,pgstream=True)
        with self.assertRaisesRegex(RuntimeError,'ROSTER_MISMATCH'):profile.runtime_environment([admin],chosen,config)
        retired=copy.deepcopy(admin);retired['Config']['Labels']['com.docker.compose.service']='feed-reader'
        with self.assertRaisesRegex(RuntimeError,'ROSTER_MISMATCH'):profile.runtime_environment([admin,retired],chosen,config,pgstream=True)
        profile.runtime_environment([admin],chosen,config,pgstream=True)
    def test_process_cpu_bookend_identity_and_missing_read(self):
        fields=['0']*30;fields[11]='12';fields[12]='8';fields[19]='100'
        with patch.object(a.os,'readlink',return_value='/usr/local/bin/pgstream'),patch.object(Path,'read_text',return_value='42 (pgstream) '+' '.join(fields)):
            value=a.process_counters('PID COMMAND RSS\n42 pgstream 123\n')['42']
        self.assertEqual((value['cpuTicks'],value['startTicks'],value['rssKiB']),(20,100,123))
        from reduce import process_deltas
        before={'42':value};after=copy.deepcopy(before);after['42']['cpuTicks']+=value['clockTicksPerSecond']
        self.assertEqual(process_deltas(before,after,2)['42']['cpuSeconds'],1)
        after['42']['startTicks']+=1
        self.assertEqual(process_deltas(before,after,2)['42']['cpu'],'UNMEASURED')
        after['42']['startTicks']-=1
        self.assertEqual(process_deltas(before,after,2)['42']['cpuSeconds'],1)
        with patch.object(Path,'read_text',side_effect=PermissionError):
            self.assertTrue(a.process_counters('PID COMMAND RSS\n42 pgstream 123\n')['42']['unavailable'])
    def test_image_pin_preserves_plugin_postgres_image(self):
        config={'services':{'postgres':{'build':{},'image':'sha256:postgres'},'evaluator':{'build':{},'image':'mutable-app'}}}
        a.pin_service_images(config,'sha256:app')
        self.assertEqual(config['services']['postgres']['image'],'sha256:postgres')
        self.assertEqual(config['services']['evaluator']['image'],'sha256:app')
    def test_prepare_uses_selected_project_pgstream_and_stable_source_env(self):
        self.check_prepared_fixture()

    def test_restore_uses_selected_image_and_complete_population(self):
        self.check_prepared_fixture(restored_count=4)
        self.check_prepared_fixture(restored_count=2)

    def check_prepared_fixture(self, restored_count=None):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);calls=[]
            args=SimpleNamespace(core_repo='core',deploy_repo='deploy',core_commit='a'*40,deploy_commit='b'*40,image='sha256:'+'c'*64,postgres_image='sha256:'+'d'*64,tenants=4,replicas=1,quiet_load=3,freeze=str(d/'freeze.json'),profile='pgstream-sample',backend_subnet='10.221.0.0/28',edge_subnet='10.221.1.0/28',fixture_project='ns-rest-joined-baseline')
            if restored_count is not None:
                (d/'source-snapshot').mkdir()
                (d/'source-snapshot/deployment.env').write_text('NS_API_REPLICAS=1\n')
                args.fixture_snapshot = str(d/'source-snapshot')
            def git(repo,*argv):
                if argv[:2]==('worktree','add'):(d/'core/deploy/multitenant').mkdir(parents=True)
                return ''
            def command(argv,**options):
                if argv[0]=='tar':
                    overlay=d/'core/deploy/multitenant'
                    for name in ('compose.yaml','commission-restore.js','publish-primer.js'):(overlay/name).write_text('synthetic')
                    return ''
                if argv[0]=='node':
                    calls.append((argv,options))
                    (d/'core/deploy/multitenant/.env').write_text('SYNTHETIC=1\nNS_API_REPLICAS=1\n')
                    if argv[1].name == 'fixture.js':
                        self.assertEqual(options['env'].get('NS_DEMO_IMAGE'), args.image)
                        primer = d/'state/primer'
                        primer.mkdir(parents=True)
                        rows = [{'id':f'00000000-0000-4000-8000-{i:012d}', 'host':f't{i}.test',
                                 'dataToken':'synthetic'} for i in range(restored_count)]
                        a.write(primer/'tenants.json', {'version':1, 'tenants':rows})
                        a.write(primer/'primed.json', {'state':'synthetic-data-primed', 'tenants':restored_count})
                        return json.dumps({'snapshot':{'version':1}, 'state':str(d/'state'), 'project':args.fixture_project})
                    return ''
                if argv[0]=='docker':
                    if argv[1:3] == ['volume','inspect']:
                        return json.dumps([{'Name':name,'CreatedAt':'synthetic'} for name in argv[3:]])
                    if argv[1] in ('network','volume'):return ''
                    names=['postgres','vault','admin','primer','feed-reader','api','realtime','evaluator','tenant-admin','ui','nginx']
                    return json.dumps({'services':{name:{'command':['postgres']if name=='postgres'else['node','entrypoint.js',name],'image':args.postgres_image if name=='postgres'else args.image}for name in names}})
                return b''
            with patch.object(a,'setup_generator') as generator,patch.object(a,'port',return_value=12345),patch.object(a,'git',side_effect=git),patch.object(a,'command',side_effect=command),patch.object(a,'inventory',return_value={}),patch.object(a,'host_identity',return_value='host'),patch.object(a,'resources',return_value=[]):
                if restored_count is not None and restored_count != args.tenants:
                    with self.assertRaisesRegex(RuntimeError, 'M7_PRIMER_COUNT'):
                        a.prepare_staged(args,d,{'sha256':'e'*64})
                    self.assertEqual(len(a.document(d/'owner.json')['restoredVolumes']), 2)
                    self.assertFalse((d/'fixture-restore.json').exists())
                    return
                a.prepare_staged(args,d,{'sha256':'e'*64})
            generator.assert_called_once()
            argv,options=calls[0]
            self.assertIn('--project',argv);self.assertEqual(argv[argv.index('--backend-subnet')+1],args.backend_subnet);self.assertEqual(argv[argv.index('--edge-subnet')+1],args.edge_subnet);self.assertEqual(options['env']['NS_PGSTREAM'],'1')
            self.assertEqual((d/'env').read_bytes(),(d/'core/deploy/multitenant/.env').read_bytes())
            lines = (d/'env').read_text().splitlines()
            self.assertEqual(len({line.split('=',1)[0] for line in lines}), len(lines))
            self.assertIn('NS_API_REPLICAS=1', lines)
            self.assertIn('SYNTHETIC=1', lines)
            self.assertEqual(a.document(d/'owner.json')['project'],args.fixture_project)
            self.assertEqual(argv[argv.index('--project')+1],args.fixture_project)
            self.assertEqual(a.document(d/'frozen.compose.json')['services']['postgres']['image'],args.postgres_image)
    def test_distinct_sql_roles_delta_and_overlap_red(self):
        roles=sql.identities({'pgstream':{'streamRole':'synthetic_stream'}},[{'A':'postgres://synthetic_adapter@invalid/synthetic'}])
        before={('synthetic_stream','1','1','00'):{'calls':2,'executionMs':1.0},('synthetic_adapter','2','1','00'):{'calls':3,'executionMs':2.0}}
        after=copy.deepcopy(before);after[('synthetic_stream','1','1','00')]['calls']+=2
        self.assertEqual(sql.assess(before,after,roles)['totals']['pgstream']['calls'],2)
        with self.assertRaisesRegex(RuntimeError,'SHARED_IDENTITY'):
            sql.identities({'pgstream':{'streamRole':'synthetic_adapter'}},[{'A':'postgres://synthetic_adapter@invalid/synthetic'}])
        with self.assertRaisesRegex(RuntimeError,'EVICTED'):sql.assess(before,{},roles)
        with self.assertRaisesRegex(RuntimeError,'COUNTER_RESET'):sql.assess(after,before,roles)
        self.assertEqual(sql.assess(before,after,roles)['totals']['pgstream']['calls'],2)
    def test_statement_reader_retains_beyond_old_top50_and_exact_query_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'snapshot.tsv';p.write_text(''.join(f'synthetic\t{i}\t{i}.0\t{i}\t1\t{str(i).encode().hex()}\n' for i in range(100)))
            self.assertEqual(len(sql.statements(p)),100)
            p.write_text('synthetic\t1\t1.0\t1\t1\t00\n'*2)
            with self.assertRaisesRegex(RuntimeError,'DUPLICATE'):sql.statements(p)

if __name__=='__main__':unittest.main()
