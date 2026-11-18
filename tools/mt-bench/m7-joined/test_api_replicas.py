"""Discovery API topology through normal projections and exact source ports.

The optional source port executes only the selected producer's pure functions.
It performs no Docker, application, HTTP or Kubernetes operation.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import adapter as a
import contract as c
import diagnostic_resources as resources
import discovery
import node_observation
import profile_provenance
import run_configuration as configuration
import static_topology
import test_static_topology as fixtures
import test_role_instances as instance_fixtures


def config(count):
    value=fixtures.config();value['prepare']['replicas']=count
    allocation=fixtures.allocation()
    for ordinal in range(3,count+1):
        allocation['services']['api-'+str(ordinal)]=dict(allocation['services']['api'])
    value['prepare']['diagnostic-resource-allocation']=json.dumps(allocation)
    return value


SOURCE_PORT=r'''
const binding=require(process.argv[1]),n=Number(process.argv[2]);
const names=['api','evaluator','evaluator-2','realtime','realtime-2'];
const participants=names.map(name=>({id:name==='api'?'api':name.includes('-')?name:name+'-1',
 roles:[name.split('-')[0]],address:{socket:'/run/ns-ipc/'+(name==='api'?'api':name.includes('-')?name:name+'-1')+'.sock'},
 ...(name.startsWith('realtime')?{slice:{count:2,ordinal:name.endsWith('-2')?1:0}}:{})}));
const peers=[{socket:'/run/ns-ipc/realtime-1.sock'},{socket:'/run/ns-ipc/realtime-2.sock'}];
const base={configs:{},environments:{},operations:{},remote:[{id:'api',endpoint:{socketPath:'/run/ns-ipc/api.sock'}}]};
for(const name of names){
 const role=name.split('-')[0],ordinal=name.endsWith('-2')?1:0;
 base.configs[name]=role==='evaluator'?{postgres:{namespaces:{checkpoint:'synthetic_checkpoint'}},
  datastore:{synthetic:true},consumer:'synthetic-evaluator',pgstream:{slot:'synthetic_slot',generation:'a'.repeat(32),
   streamRole:'synthetic_stream',transactionRows:1000,receiver:{url:'http://'+name+':19913/'}}}:
  role==='realtime'?{completedOutput:{namespace:'synthetic_checkpoint',consumer:'synthetic-evaluator'}}:{};
 base.environments[name]={NS_API_INTERNAL_SOCKET:'/run/ns-ipc/api.sock',
  NS_SERVE_INTERNAL_SOCKET:'/run/ns-ipc/'+(role==='api'?'api':role+'-'+(ordinal+1))+'.sock'};
 if(role==='evaluator')Object.assign(base.environments[name],{NS_PGSTREAM_EVALUATOR_SLICE:JSON.stringify({count:2,ordinal,
  receivers:['http://evaluator:19913/','http://evaluator-2:19913/']}),NS_REALTIME_SLICE_PEERS:JSON.stringify(peers)});
 if(role==='realtime')base.environments[name].NS_REALTIME_SLICE=JSON.stringify({count:2,ordinal});
 base.operations[name]={participantId:role==='api'?'api':role+'-'+(ordinal+1),participants};
}
for(const bad of [0,17,true]){let rejected=false;try{binding.expand(base,bad);}catch{rejected=true;}if(!rejected)throw Error('SOURCE_INVALID_COUNT_ADMITTED');}
if(binding.count({NS_API_REPLICAS:String(n)})!==n)throw Error('SOURCE_CHANGED_COUNT');
const docs=binding.expand(base,n);
const processes=Object.entries(docs.operations).map(([name,operation])=>({name,roles:[name.split('-')[0]],
 environment:docs.environments[name],files:{'/run/ns-config/config.json':docs.configs[name],'/run/ns-config/operation.json':operation}}));
console.log(JSON.stringify({compose:binding.compose(n),documents:{contract:1,processes}}));
'''


class ApiReplicas(unittest.TestCase):
    def setUp(self):
        self.pin=patch.object(a,'instrument',return_value={'sha256':'d'*64});self.pin.start();self.addCleanup(self.pin.stop)

    def test_normal_cli_projection_receipt_and_worker_bound(self):
        for count in (3,16):
            value=config(count);projected=configuration.resolve(value)
            selected=projected['configuration']
            self.assertEqual(selected['replicas'],count)
            self.assertEqual(projected['receiptLimits']['apiReplicas'],count)
            self.assertEqual(projected['receiptLimits']['staticWorkers'],2)
            proof={**projected['diagnosticReceiptTemplate'],'status':'AUTHORIZED_DIAGNOSTIC'}
            m={**selected,'instrument':{'sha256':'d'*64},'runConfiguration':selected}
            c.receipt_scope(m,proof,'run')
            for change in ({'apiReplicas':2},{'apiReplicas':True}):
                bad=copy.deepcopy(proof);bad['limits'].update(change)
                with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_LIMIT_INVALID'):c.receipt_scope(m,bad,'run')
            bad=copy.deepcopy(proof);bad['pair']['core']='0'*40
            with self.assertRaisesRegex(RuntimeError,'M7_RECEIPT_SOURCE_MISMATCH'):c.receipt_scope(m,bad,'run')
            args=fixtures.parsed(value);args.node_observation='profile-v1';args.load_seconds=310
            self.assertEqual(node_observation.option(args),{'nodeObservationMode':'profile-v1'})
        for bad in (0,17,True):
            self.assertFalse(c.discovery_api_replicas(bad))
            with self.assertRaises((RuntimeError,ValueError)):configuration.resolve(config(bad))
        self.assertEqual(static_topology.validate(fixtures.manifest(k=8,n=3))['workers'],8)
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_TOPOLOGY'):
            static_topology.validate(fixtures.manifest(k=9,n=3))
        self.assertEqual(c.REPLICAS,(1,2,4))
        legacy=config(3);legacy['prepare'].pop('static-workers');legacy['prepare'].update({'run-purpose':'acceptance'})
        legacy['tier']='acceptance'
        with self.assertRaises(RuntimeError):configuration.resolve(legacy)

    def test_eight_workers_bind_exact_receipt(self):
        value=config(3)
        allocation=json.loads(value['prepare']['diagnostic-resource-allocation'])
        for role in ('evaluator','realtime'):
            for ordinal in range(3,9):
                allocation['services'][f'{role}-{ordinal}']=dict(allocation['services'][role])
        value['prepare']['static-workers']=8
        value['prepare']['diagnostic-resource-allocation']=json.dumps(allocation)
        result=configuration.resolve(value)
        self.assertEqual(result['receiptLimits']['staticWorkers'],8)
        selected=result['configuration']
        proof={**result['diagnosticReceiptTemplate'],'status':'AUTHORIZED_DIAGNOSTIC'}
        manifest={**selected,'instrument':{'sha256':'d'*64},'runConfiguration':selected}
        c.receipt_scope(manifest,proof,'run')
        proof['limits']['staticWorkers']=4
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_RECEIPT'):
            static_topology.receipt(selected,proof)

    def test_explicit_allocation_remains_required_and_aggregate_checked(self):
        value=config(3);allocation=json.loads(value['prepare']['diagnostic-resource-allocation'])
        selected=resources.selection(allocation)
        bad=copy.deepcopy(allocation);bad['ceiling']['millicpus']=1
        value['prepare']['diagnostic-resource-allocation']=json.dumps(bad)
        with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_RESOURCE_ALLOCATION_AGGREGATE_EXCEEDED'):
            configuration.resolve(value)
        value=config(3);value['prepare'].pop('diagnostic-resource-allocation')
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_EXPLICIT_ALLOCATION'):configuration.resolve(value)
        self.assertIn('api-3',selected['services'])

    def test_discovery_reader_retains_scope_and_legacy_profile_grid(self):
        from test_contract import PROFILE
        value={'version':1,'kind':'m7-joined-discovery-cell','runPurpose':'discovery','status':'PARTIAL',
               'capacityAcceptance':'NOT_GRANTED','pair':{'core':'a'*40,'deploy':'b'*40},
               'instrument':'d'*64,'hostIdentity':'c'*64,'imageId':'sha256:'+'e'*64,
               'profileSelection':PROFILE,'settingsFingerprint':{'sha256':'f'*64,'sourceCommit':'a'*40},
               'owner':'f'*32,'ownershipVerified':True,'tenants':2,'strictChecks':{},'processes':{},
               'hardFailures':[],'oracle':None,'profile':'pgstream-sample',**c.UNACCEPTED_SCOPE}
        for count in (3,16):
            discovery.check_discovery({**value,'replicas':count})
        for bad in (0,17,True):
            with self.assertRaisesRegex(RuntimeError,'M7_DISCOVERY_TOPOLOGY'):
                discovery.check_discovery({**value,'replicas':bad})
        with self.assertRaisesRegex(RuntimeError,'M7_DISCOVERY_TOPOLOGY'):
            discovery.check_discovery({**value,'profile':'remote-pilot','replicas':3})

    @unittest.skipUnless(os.environ.get('M7_API_REPLICAS_SOURCE_FILE'),'exact selected producer source not supplied')
    def test_exact_source_generated_service_documents_and_every_api_reader(self):
        import yaml
        source=Path(os.environ['M7_API_REPLICAS_SOURCE_FILE'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),os.environ['M7_API_REPLICAS_SOURCE_SHA256'])
        for count in (3,16):
            generated=json.loads(subprocess.check_output(['node','-e',SOURCE_PORT,str(source),str(count)],text=True))
            selected=configuration.resolve(config(count))['configuration']
            allocation=selected['resources']['profile']
            cfg={'services':{name:{} for name in allocation['services']}}
            cfg['services'].update(instance_fixtures.config(k=2,apis=1)['services'])
            overlay=yaml.safe_load(generated['compose'])
            for name,spec in overlay['services'].items():
                if name=='api' or name.startswith('api-'):
                    cfg['services'][name]={**copy.deepcopy(cfg['services']['api']),**spec}
            cfg['services']['bootstrap']['environment']={'NS_DEMO_TENANTS':str(selected['tenants'])}
            for name,spec in cfg['services'].items():
                if name.startswith(('evaluator','realtime')):spec['restart']='unless-stopped'
            cfg['services']['socket-edge']={'command':static_topology.EDGE_COMMAND,'restart':'unless-stopped','environment':{
                'NS_REALTIME_STATIC_COUNT':'2','NS_REALTIME_STATIC_ROUTE_MAP':json.dumps({'version':1,'rule':'sha256-modulo-v1',
                    'count':2,'upstreams':['http://realtime:1339/','http://realtime-2:1339/']})}}
            actual=static_topology.verify_config(selected,cfg)
            self.assertEqual(sum(row['role']=='api' for row in actual.values()),count)
            self.assertEqual(static_topology.verify_documents(selected,generated['documents'])['status'],'VERIFIED')
            bounded=resources.overlay(cfg,allocation);resources.verify_config(bounded,resources.plan(bounded))
            self.assertEqual(len([name for name in profile_provenance.log_roles(cfg) if name=='api' or name.startswith('api-')]),count)
            broken=copy.deepcopy(cfg);broken['services'].pop('api-'+str(count))
            with self.assertRaisesRegex(RuntimeError,'M7_INSTANCE_API_COVERAGE'):static_topology.verify_config(selected,broken)
            bad_docs=copy.deepcopy(generated['documents']);bad_docs['processes'].pop()
            with self.assertRaisesRegex(RuntimeError,'M7_STATIC_DOCUMENT_COVERAGE'):static_topology.verify_documents(selected,bad_docs)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'state').mkdir()
                m={**selected,'owner':'a'*32,'diagnostics':profile_provenance.selection()}
                # The source port emits a Compose overlay. The observer consumes
                # normalized Compose JSON; exercise its canonical unit fixture
                # with exactly the source-derived serving-service roster.
                node_config=instance_fixtures.config(k=2,apis=count)
                self.assertEqual(set(node_config['services']),set(actual))
                node_observation.install(node_config,root,m,'profile-v1')
                self.assertEqual(len(m['nodeObservation']['instances']),count+4)
                node_observation.verify(node_config,root,m)


if __name__=='__main__':unittest.main()
