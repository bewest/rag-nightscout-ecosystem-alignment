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
CORE, DEPLOY = 'ce96241b390cd5397d808417b353161eed83e564', '160ca4d62002746c9b1401dc4784ba30b8543711'
from test_run_configuration import config as legacy_config, parsed
import test_evaluator_progress as fixture_progress
from test_evaluator_progress import A, B, R, S


def config():
    value=legacy_config();value['prepare'].update({'core-commit':CORE,'deploy-commit':DEPLOY,
        'pgstream-topology':'external-service-v1','completion-contract':'evaluator-work-v2','static-workers':2,'replicas':2,
        'generator-dependencies':'/synthetic/owned-dependencies'})
    return value


def manifest(k=2,n=2):
    return {'pair':{'core':CORE,'deploy':DEPLOY},'profile':'pgstream-sample','runPurpose':'discovery',
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

    def test_any_pair_is_admitted_without_a_build_receipt_and_recorded(self):
        # Run identity is image digest + configuration: no legacy pair list, no build receipt.
        cfg = config();cfg['prepare'].update({'core-commit': '1'*40, 'deploy-commit': '2'*40})
        projection = rc.resolve(cfg);m = projection['configuration']
        self.assertEqual(m['pair'], {'core': '1'*40, 'deploy': '2'*40})
        self.assertNotIn('staticBuildReceiptSha256', m)
        self.assertIn('imageId', m)
        self.assertEqual(s.validate(m), {'kind': s.KIND, 'workers': 2})
        self.assertEqual(projection['diagnosticReceiptTemplate']['pair'], m['pair'])
        for pair in ({'core': '1'*40, 'deploy': 'short'}, {'core': '1'*40, 'deploy': '2'*40, 'ancestor': True}, {'core': [], 'deploy': '2'*40}):
            with self.assertRaisesRegex(RuntimeError, 'M7_STATIC_SOURCE_PAIR'):s.validate({**m, 'pair': pair})

    def test_source_and_count_flags_reach_ordinary_preparation_environment(self):
        m=manifest();self.assertEqual(s.environment(m),{'NS_EVALUATOR_WORKERS':'2','NS_REALTIME_WORKERS':'2'})
        self.assertEqual(s.environment({}),{})
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_SOURCE_PAIR'):s.validate({**m,'pair':{'core':'a'*39,'deploy':DEPLOY}})

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
