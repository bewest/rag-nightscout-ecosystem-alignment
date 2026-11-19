"""Exact static diagnostic admission, parser and launch controls, no capacity claim."""
import copy
import json
import hashlib
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import adapter as a
import contract as c
import evaluator_progress as ep
import run_configuration as rc
import runner
import static_topology as s
from test_run_configuration import config as legacy_config, parsed
import test_evaluator_progress as fixture_progress
from test_evaluator_progress import A, B, R, S


def config():
    value=legacy_config();value['prepare'].update({'core-commit':s.CORE,'deploy-commit':s.DEPLOY,
        'pgstream-topology':'external-service-v1','completion-contract':'evaluator-work-v2','static-workers':2,'replicas':2,
        'generator-dependencies':'/synthetic/owned-dependencies'})
    return value


def manifest(k=2,n=2):
    return {'pair':{'core':s.CORE,'deploy':s.DEPLOY},'profile':'pgstream-sample','runPurpose':'discovery',
            'pgstreamTopology':'external-service-v1','completionContract':'evaluator-work-v2','replicas':n,
            'staticTopology':{'kind':s.KIND,'workers':k}}


class StaticTopology(unittest.TestCase):
    def setUp(self):
        self.pin=patch.object(a,'instrument',return_value={'sha256':'d'*64});self.pin.start();self.addCleanup(self.pin.stop)

    def test_explicit_selection_and_exact_v2_receipt_mirrors(self):
        cfg=config();args=parsed(cfg);projection=rc.resolve(cfg)
        self.assertEqual(projection['configuration']['staticTopology'],{'kind':s.KIND,'workers':2})
        self.assertEqual(projection['receiptLimits']['staticWorkers'],2)
        m={**projection['configuration'],'instrument':{'sha256':'d'*64},'runConfiguration':projection['configuration']}
        proof={**projection['diagnosticReceiptTemplate'],'status':'AUTHORIZED_DIAGNOSTIC'}
        self.assertEqual(c.receipt_scope(m,proof,'run')['capacityAcceptance'],'NOT_GRANTED')
        self.assertEqual(c.receipt_scope(m,proof,'deploy')['functionalAcceptance'],'PENDING')
        self.assertEqual(rc.from_manifest(m),projection['configuration'])
        for mutate,code in ((lambda p:p.update(version=1),'M7_STATIC_RECEIPT'),
                            (lambda p:p['limits'].update(staticWorkers=1),'M7_STATIC_RECEIPT'),
                            (lambda p:p['limits'].update(apiReplicas=1),'M7_DIAGNOSTIC_LIMIT_INVALID')):
            bad=copy.deepcopy(proof);mutate(bad)
            with self.assertRaisesRegex(RuntimeError,code):c.receipt_scope(m,bad,'deploy')
        bad=copy.deepcopy(m);bad['runConfiguration'].pop('staticTopology');badproof=copy.deepcopy(proof);badproof['configurationSha256']=rc.sha(bad['runConfiguration'])
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_CONFIGURATION_MISMATCH'):c.receipt_scope(bad,badproof,'run')
        self.assertEqual(c.receipt_scope(m,proof,'run')['functionalAcceptance'],'PENDING')

    def test_pinned_build_admits_new_pair_and_binds_authorization(self):
        cfg = config()
        options = cfg['prepare']
        pair = {'coreCommit': '1'*40, 'deployCommit': '2'*40}
        image = 'sha256:' + '3'*64
        lock = b'package lock from selected core'
        producer = '4'*64
        options.update({'core-commit': pair['coreCommit'], 'deploy-commit': pair['deployCommit'],
                        'image': image, 'image-id': image})
        proof = {'schemaVersion': 1, 'basis': 'reproduced', 'status': 'BUILT_VERIFIED_LOCAL',
                 **pair, 'localImageId': image,
                 'labels': {'org.opencontainers.image.revision': pair['coreCommit'],
                            'org.nightscout.deploy.revision': pair['deployCommit']},
                 'runtime': {'source': {'version': 1, **pair}, 'binarySha256': producer,
                             'producerHelpSucceeded': True, 'lockSha256': hashlib.sha256(lock).hexdigest()}}
        with TemporaryDirectory() as tmp, patch.object(a, 'command', return_value=lock), \
                patch.object(a, 'git', return_value=json.dumps({'binarySha256': producer})):
            path = Path(tmp) / 'build.json'
            def put(value):
                path.write_text(json.dumps(value))
                options.update({'static-build-receipt': str(path), 'static-build-receipt-sha256': a.digest(path)})
            put(proof)
            projected = rc.resolve(cfg)
            value = projected['configuration']
            self.assertEqual(value['staticBuildReceiptSha256'], a.digest(path))
            manifest = {**value, 'instrument': {'sha256': 'd'*64}, 'runConfiguration': value}
            auth = {**projected['diagnosticReceiptTemplate'], 'status': 'AUTHORIZED_DIAGNOSTIC'}
            self.assertEqual(c.receipt_scope(manifest, auth, 'deploy')['functionalAcceptance'], 'PENDING')
            self.assertEqual(rc.from_manifest(manifest)['staticBuildReceiptSha256'], a.digest(path))
            with self.assertRaisesRegex(RuntimeError, 'M7_STATIC_CONFIGURATION_MISMATCH'):
                c.receipt_scope({**manifest, 'staticBuildReceiptSha256': 'f'*64}, auth, 'deploy')
            put({**proof, 'localImageId': 'sha256:'+'9'*64})
            with self.assertRaisesRegex(RuntimeError, 'M7_STATIC_BUILD_IDENTITY'):
                rc.resolve(cfg)
            # Build provenance is recorded by the build, not re-proved per run.
            for field, change in [('deployCommit', '3'*40), ('runtime', {**proof['runtime'], 'source': {}}),
                                  ('runtime', {**proof['runtime'], 'lockSha256': '9'*64})]:
                put({**proof, field: change})
                rc.resolve(cfg)
            put(proof)
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(RuntimeError, 'M7_STATIC_BUILD_RECEIPT_DIGEST'):
                rc.resolve(cfg)
            put(proof)
            self.assertEqual(rc.resolve(cfg)['configurationSha256'], projected['configurationSha256'])

    def test_actual_prepare_static_receipt_passes_before_dependency_or_image_effects(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=config();projection=rc.resolve(cfg);args=parsed(cfg)
            args.directory=str(root/'fixture');args.freeze=str(root/'receipt.json')
            proof={**projection['diagnosticReceiptTemplate'],'status':'AUTHORIZED_DIAGNOSTIC'};a.write(args.freeze,proof)
            with ExitStack() as stack:
                from test_stream_topology import source_schema
                stack.enter_context(patch.object(a,'git',return_value=json.dumps(source_schema())))
                stack.enter_context(patch.object(a,'commit',side_effect=lambda repo,head:head))
                stack.enter_context(patch.object(a,'unused_project_namespace'))
                # Configuration v2 now checks its exact unused namespaces before
                # dependency/image work. Keep this offline boundary explicit.
                stack.enter_context(patch.object(rc,'namespace_preflight',return_value={}))
                deps=stack.enter_context(patch.object(a,'qualified_dependencies',side_effect=RuntimeError('STOP_AFTER_STATIC_RECEIPT')))
                image=stack.enter_context(patch.object(a,'prepare_image_inputs'))
                with self.assertRaisesRegex(RuntimeError,'STOP_AFTER_STATIC_RECEIPT'):a.prepare(args)
                deps.assert_called_once();image.assert_not_called();self.assertFalse(Path(args.directory).exists())
                deps.reset_mock();proof['limits']['staticWorkers']=1;a.write(args.freeze,proof)
                with self.assertRaisesRegex(RuntimeError,'M7_STATIC_RECEIPT'):a.prepare(args)
                deps.assert_not_called();image.assert_not_called()

    def test_static_v1_refuses_in_runner_before_output_or_window_then_restores(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp);cfg = config();projection = rc.resolve(cfg)
            proof = {**projection['diagnosticReceiptTemplate'], 'status': 'AUTHORIZED_DIAGNOSTIC'}
            proof_path = root / 'receipt.json';cfg['prepare']['receipt'] = str(proof_path)
            cfg_path = root / 'config.json';a.write(cfg_path, cfg)
            a.write(proof_path, {**proof, 'version': 1})
            with patch.object(runner, 'arm_window') as arm, patch.object(runner, 'stage') as stage:
                with self.assertRaisesRegex(RuntimeError, 'M7_STATIC_RECEIPT'):
                    runner.prepare(cfg_path, root / 'not-created')
                arm.assert_not_called();stage.assert_not_called()
            self.assertFalse((root / 'not-created').exists())
            _, argv = runner.validate_config(cfg)
            import inspect
            source = inspect.getsource(runner.preflight_receipt)
            broken = source.replace(" or parsed.static_workers is not None", '')
            self.assertNotEqual(source, broken)
            scope = {'a': a};exec(compile(broken, 'runner_static_v1_control', 'exec'), scope)
            def criterion(fn):
                try: fn(cfg, argv)
                except RuntimeError as error:
                    self.assertEqual(str(error), 'M7_STATIC_RECEIPT');return
                raise AssertionError('STATIC_V1_MUST_REFUSE_BEFORE_WINDOW')
            criterion(runner.preflight_receipt)
            with self.assertRaisesRegex(AssertionError, 'STATIC_V1_MUST_REFUSE_BEFORE_WINDOW'):
                criterion(scope['preflight_receipt'])
            criterion(runner.preflight_receipt)
            a.write(proof_path, proof);runner.preflight_receipt(cfg, argv)
            # The original unselected v1 path stays under the adapter's legacy gate.
            legacy = legacy_config();legacy['prepare']['receipt'] = str(proof_path)
            a.write(proof_path, {'version': 1})
            _, legacy_argv = runner.validate_config(legacy)
            runner.preflight_receipt(legacy, legacy_argv)

    def test_legacy_restrictions_and_wrong_source_mode_allocation_refuse(self):
        legacy=legacy_config();legacy['prepare']['replicas']=2
        with self.assertRaisesRegex(RuntimeError,'M7_CONFIG_SINGLE_API_TENANT_RANGE'):parsed(legacy)
        for field,value,code in (('core-commit','a'*40,'M7_STATIC_SOURCE_PAIR'),('deploy-commit','b'*40,'M7_STATIC_SOURCE_PAIR'),
                                 ('pgstream-topology','colocated-v1','M7_STATIC_DIAGNOSTIC_SCOPE'),('completion-contract','evaluator-work-v1','M7_STATIC_DIAGNOSTIC_SCOPE')):
            bad=config();bad['prepare'][field]=value
            with self.assertRaisesRegex(RuntimeError,code):parsed(bad)
        good=config();parsed(good)

    def test_single_worker_and_api_have_no_service_caps(self):
        cfg = config()
        cfg['prepare'].update({'static-workers': 1, 'replicas': 1})
        args = parsed(cfg)
        self.assertEqual(s.option(args)['staticTopology'], {'kind': s.KIND, 'workers': 1})
        self.assertNotIn('resources', rc.from_args(args, a.instrument()['sha256']))
        # Multi-worker or multi-API runs uncapped Compose services.
        for changes in ({'static-workers': 2}, {'replicas': 2}):
            other = {**cfg, 'prepare': {**cfg['prepare'], **changes}}
            self.assertEqual(s.option(parsed(other))['staticTopology']['kind'], s.KIND)
            self.assertNotIn('resources', rc.from_args(parsed(other), a.instrument()['sha256']))
        self.assertEqual(s.option(parsed(cfg))['staticTopology']['workers'], 1)

    def test_each_published_exact_pair_has_config_receipt_and_unknown_pair_refusal(self):
        for core, deploy in s.SOURCE_PAIRS:
            cfg = config();cfg['prepare'].update({'core-commit': core, 'deploy-commit': deploy})
            projection = rc.resolve(cfg);m = projection['configuration']
            self.assertEqual(m['pair'], {'core': core, 'deploy': deploy})
            self.assertEqual(s.validate(m), {'kind': s.KIND, 'workers': 2})
            self.assertEqual(projection['diagnosticReceiptTemplate']['pair'], m['pair'])
            for pair in ({'core': core, 'deploy': 'a' * 40}, {'core': 'b' * 40, 'deploy': deploy},
                         {'core': core, 'deploy': deploy, 'ancestor': True}, {'core': [], 'deploy': deploy}):
                with self.assertRaisesRegex(RuntimeError, 'M7_STATIC_SOURCE_PAIR'):s.validate({**m, 'pair': pair})
            self.assertEqual(s.validate(m), {'kind': s.KIND, 'workers': 2})

    def test_source_and_count_flags_reach_ordinary_preparation_environment(self):
        m=manifest();self.assertEqual(s.environment(m),{'NS_EVALUATOR_WORKERS':'2','NS_REALTIME_WORKERS':'2'})
        self.assertEqual(s.environment({}),{})
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_SOURCE_PAIR'):s.validate({**m,'pair':{'core':'a'*40,'deploy':s.DEPLOY}})

    def test_socket_edge_is_explicit_in_existing_launch_and_readiness_roster(self):
        config={'services':{}}
        for role in ('api','api-2','evaluator','evaluator-2','realtime','realtime-2','tenant-admin'):
            family=role if role=='tenant-admin' else role.split('-')[0]
            config['services'][role]={'command':['node','deploy/multitenant/entrypoint.js',family]}
        config['services']['pgstream']={'command':a.stream_topology.EXTERNAL_COMMAND}
        config['services']['socket-edge']={'command':s.EDGE_COMMAND}
        roster=a.service_roster(config)
        self.assertIn('socket-edge',roster)
        stages=a.deployment_plan(config,pgstream=True)
        self.assertEqual(next(row[2][-2:] for row in stages if row[0]=='apis'),['api','api-2'])
        launch=next(row[2] for row in stages if row[0]=='remaining-roles')
        for role in ('evaluator','evaluator-2','realtime','realtime-2','pgstream','socket-edge'):self.assertIn(role,launch)
        broken=copy.deepcopy(config);broken['services']['socket-edge']['command']=['node','other.js']
        self.assertNotIn('socket-edge',a.service_roster(broken))
        self.assertIn('socket-edge',a.service_roster(config))

    def test_runtime_edge_and_attached_original_owner_refuse_missing_or_foreign(self):
        from test_role_instances import config as role_config, rows as role_rows
        from contract import OWNER
        cfg=role_config();m={**manifest(),'owner':'a'*32,'project':'ns-static-test','imageId':'sha256:'+'b'*64}
        for name,row in cfg['services'].items():
            if name.startswith(('evaluator','realtime')):row['restart']='unless-stopped'
        cfg['services']['socket-edge']={'command':s.EDGE_COMMAND,'restart':'unless-stopped','environment':{
            'NS_REALTIME_STATIC_COUNT':'2','NS_REALTIME_STATIC_ROUTE_MAP':json.dumps({'version':1,'rule':'sha256-modulo-v1','count':2,'upstreams':['http://realtime:1339/','http://realtime-2:1339/']})}}
        values=role_rows({'services':{k:v for k,v in cfg['services'].items() if k!='socket-edge'}},m)
        edge={'Id':'physical-edge','Image':m['imageId'],'Config':{'Cmd':s.EDGE_COMMAND,'Labels':{OWNER:m['owner'],'com.docker.compose.project':m['project'],'com.docker.compose.service':'socket-edge'}},'State':{'Running':True,'Pid':90,'StartedAt':'2026-11-17T00:00:00Z'}}
        values.append(edge);self.assertEqual(s.verify_runtime(m,cfg,values)['status'],'VERIFIED')
        for bad in (values[:-1],values+values[-1:]):
            with self.assertRaisesRegex(RuntimeError,'M7_STATIC_EDGE_RUNTIME'):s.verify_runtime(m,cfg,bad)
        attached={**m,'attached':True,'owner':'c'*32,'runtimeOwnerLabels':['a'*32]}
        self.assertEqual(s.verify_runtime(attached,cfg,values)['status'],'VERIFIED')
        attached['runtimeOwnerLabels']=['d'*32]
        with self.assertRaisesRegex(RuntimeError,'M7_INSTANCE_RUNTIME_IDENTITY'):s.verify_runtime(attached,cfg,values)
        self.assertEqual(s.verify_runtime(m,cfg,values)['status'],'VERIFIED')

    def test_static_inspection_preserves_configuration_and_unknown_peer_liveness(self):
        fixture=fixture_progress.Progress();frames={}
        for name,ordinal,rid,owner in [('evaluator',0,R,A),('evaluator-2',1,S,B)]:
            frame=fixture.frame(ids=[A,B],ordinal=ordinal,runtime=rid)
            frame.update(selfMode='static',selfCount=2)
            frame['view']['configured'].update(mode='static',count=2,rule='sha256-modulo-v1',leaseMs=None)
            frame['view']['observed']=None;frame['view']['gate']['members']=2
            for row in frame['view']['tenants']:
                row['admitted']=row['tenant']==owner
                if not row['admitted']:row['ready']=False
            frames[name]=frame
        def check(values):return ep.round_view(['evaluator','evaluator-2'],[A,B],lambda service,*_:json.dumps(values[service]))
        original_round=check(frames)
        self.assertEqual(set(original_round['owners']),{A,B})
        packed=ep.pack({'rounds':[original_round,original_round,original_round]})
        packed['attribution']={'staticTopology':{'kind':s.KIND,'workers':2}}
        ep.decode_rounds(packed,2,['evaluator','evaluator-2'])
        omitted=copy.deepcopy(packed)
        for row in omitted['rounds'][0]['instances'].values():row.pop('static')
        with self.assertRaisesRegex(ep.Refused,'M7_EVALUATOR_STATIC_CONFIGURATION'):ep.decode_rounds(omitted,2,['evaluator','evaluator-2'])
        ep.decode_rounds(packed,2,['evaluator','evaluator-2'])
        for field,value in [('count',1),('rule','wrong'),('leaseMs',10)]:
            bad=copy.deepcopy(frames);bad['evaluator-2']['view']['configured'][field]=value
            with self.assertRaisesRegex(ep.Refused,'M7_EVALUATOR_STATIC_CONFIGURATION'):check(bad)
        bad=copy.deepcopy(frames);bad['evaluator']['view']['observed']={'members':2}
        with self.assertRaisesRegex(ep.Refused,'M7_EVALUATOR_STATIC_CONFIGURATION'):check(bad)
        self.assertEqual(len(check(frames)['instances']),2)


if __name__=='__main__':unittest.main()
