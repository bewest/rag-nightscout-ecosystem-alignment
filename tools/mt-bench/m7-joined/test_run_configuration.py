"""Actual receipt, runner and remote CLI guarantees with synthetic inputs only."""
import copy
import inspect
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import adapter as a
import contract as c
import discovery
import run_configuration as rc
import runner

REMOTE=Path(__file__).resolve().parent.parent/'remote-pgstream'
previous_path=list(sys.path)
try:
    sys.path.insert(0,str(REMOTE))
    import protocol
    import cell
    import transport
finally:
    sys.path[:]=previous_path


def config():
    value=json.loads((Path(__file__).parent/'examples/local-rehearsal.json').read_text())
    value.pop('helperHead');value['helperInstrument']='d'*64
    value['prepare'].update({'logical-polling-clients':4,'probe-every-ms':3000,'sockets-per-tenant':2,
                            'jwt-setup-concurrency':1})
    value['k6Image']='sha256:'+'e'*64
    return value


def parsed(value):
    _,argv=runner.validate_config(value)
    return a.parser().parse_args(['prepare','--directory','/tmp/synthetic-only',*argv])


def packet(value):
    r=rc.from_args(parsed(value),'d'*64)
    m={**r,'instrument':{'sha256':'d'*64},'runConfiguration':r}
    receipt={'version':2,'kind':'joined-diagnostic','status':'AUTHORIZED_DIAGNOSTIC',
             'purpose':'BOUNDED_DISCOVERY','pair':r['pair'],'imageId':r['imageId'],'instrument':'d'*64,
             'functionalAcceptanceAtAuthorization':'PENDING','sourceAcceptance':{'status':'PENDING'},
             'configurationSha256':rc.sha(r),'execution':{k:value[k] for k in ('workSeconds','cleanupSeconds','k6Image')},'limits':{'tenants':r['tenants'],'apiReplicas':1,'trafficSeconds':r['cadence']['loadSeconds']}}
    return m,receipt


def overlay():
    return {'binding':{'version':1,'profile':protocol.PROFILE,'runId':'synthetic-run',
        'cloudId':'synthetic-run-'+'a'*12,'nonce':'b'*32,'cell':1,
        'appAddress':'10.1.1.1','generatorAddress':'10.1.1.2','port':18080,
        'expiresAt':time.time()+2000,'sourceSha256':'f'*64,
        'transport':{'interface':'eth1','mac':'00:11:22:33:44:55','approvedAddress':'10.1.1.1','approvalReference':'synthetic-only'}},
        'resourceReference':'synthetic-only','hostInventory':{
            'sut':{'providerId':'synthetic-sut','cpuCores':8,'ramBytes':16*1024**3},
            'driver':{'providerId':'synthetic-driver','cpuCores':4,'ramBytes':8*1024**3}}}


class Configuration(unittest.TestCase):
    def setUp(self):
        self.pin=patch.object(a,'instrument',return_value={'sha256':'d'*64});self.pin.start();self.addCleanup(self.pin.stop)

    def test_api_cause_observer_is_bound_in_both_configuration_projections(self):
        cfg=config();plain=rc.from_args(parsed(cfg),'d'*64)
        cfg['prepare']['api-cause-observation']='on';observed=rc.from_args(parsed(cfg),'d'*64)
        self.assertNotIn('apiCauseObservation',plain);self.assertEqual(observed['apiCauseObservation'],'on')
        self.assertNotEqual(rc.sha(plain),rc.sha(observed))
        manifest={**observed,'instrument':{'sha256':'d'*64},'apiCause':{'roles':['api']}}
        self.assertEqual(rc.from_manifest(manifest),observed)
        manifest.pop('apiCause');self.assertNotIn('apiCauseObservation',rc.from_manifest(manifest))

    def test_readiness_changes_configuration_hash_and_has_no_unbound_remote_projection(self):
        cfg=config();cfg['prepare']['tenant-readiness']='serve'
        serve=rc.from_args(parsed(cfg),'d'*64)
        cfg['prepare']['tenant-readiness']='all';all_tenants=rc.from_args(parsed(cfg),'d'*64)
        self.assertNotEqual(rc.sha(serve),rc.sha(all_tenants))
        manifest={**serve,'instrument':{'sha256':'d'*64}}
        self.assertEqual(rc.from_manifest(manifest),serve)
        with self.assertRaisesRegex(RuntimeError,'REMOTE_STARTUP_SELECTION'):
            rc.remote_projection(cfg,overlay())

    def test_legacy_pending_and_strict_acceptance_stay_compatible(self):
        m,r=packet(config());r.pop('version');r.pop('sourceAcceptance');r.pop('configurationSha256');r.pop('purpose')
        self.assertEqual(c.receipt_scope(m,r,'run')['functionalAcceptance'],'UNACCEPTED')
        with self.assertRaisesRegex(RuntimeError,'RECEIPT_REQUIRED'):
            c.receipt_scope(m,{**r,'functionalAcceptanceAtAuthorization':'PASS'},'run')
        strict={'pair':m['pair'],'kind':'joined-acceptance','status':'PASS','evidenceSha256':'a'*64}
        self.assertEqual(c.receipt_scope({**m,'runPurpose':'acceptance'},strict,'run')['kind'],'accepted-capacity')
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'strict.json';a.write(file,{**strict,'version':2})
            self.assertEqual(a.frozen({**m,'runPurpose':'acceptance','prepared':True,'freeze':str(file)},'run')['kind'],'accepted-capacity')

    def test_v2_pending_and_pass_evidence_and_no_promotion(self):
        m,r=packet(config())
        self.assertEqual(c.receipt_scope(m,r,'run')['functionalAcceptance'],'PENDING')
        with tempfile.TemporaryDirectory() as tmp:
            evidence=Path(tmp)/'acceptance.json'
            evidence.write_text(json.dumps({'kind':'joined-acceptance','status':'PASS','pair':m['pair'],
                'imageId':m['imageId'],'instrument':'a'*64,'evidenceSha256':'b'*64}))
            r.update(functionalAcceptanceAtAuthorization='PASS',sourceAcceptance={'status':'PASS','reference':str(evidence),'sha256':a.digest(evidence)})
            scope=c.receipt_scope(m,r,'run');self.assertEqual(scope['functionalAcceptance'],'PASS')
            result={'runPurpose':'discovery',**scope}
            c.check_discovery_scope(result)
            with self.assertRaisesRegex(RuntimeError,'DISCOVERY_NOT_ACCEPTANCE'):c.accepted_claim_scope(result)
            for mutate in (lambda v:v.update(imageId='sha256:'+'0'*64),lambda v:v.update(status='FAIL')):
                doc=json.loads(evidence.read_text());mutate(doc);evidence.write_text(json.dumps(doc))
                r['sourceAcceptance']['sha256']=a.digest(evidence)
                with self.assertRaisesRegex(RuntimeError,'ACCEPTANCE_TUPLE'):c.receipt_scope(m,r,'run')
            evidence.unlink()
            with self.assertRaisesRegex(RuntimeError,'ACCEPTANCE_EVIDENCE'):c.receipt_scope(m,r,'run')
        for status in ('FAIL','UNKNOWN',True):
            with self.assertRaisesRegex(RuntimeError,'ACCEPTANCE_STATUS'):
                c.receipt_scope(m,{**r,'sourceAcceptance':{'status':status}},'run')

    def test_actual_runner_refuses_tamper_before_output_guard_or_effects(self):
        for key,value in (('load-seconds',31),('core-commit','0'*40),('logical-polling-clients',5),
                          ('diagnostic-resource-profile',a.diagnostic_resources.EXTERNAL_NAME),('tenant-readiness','all')):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                cfg=config();m,r=packet(cfg);root=Path(tmp);receipt=root/'receipt.json';a.write(receipt,r)
                cfg['prepare']['receipt']=str(receipt);cfg['prepare'][key]=value
                if key=='diagnostic-resource-profile':
                    cfg['prepare'].update({'pgstream-topology':'external-service-v1','generator-dependencies':'/synthetic'})
                file=root/'run.json';a.write(file,cfg);target=root/'never-created'
                with patch.object(runner,'arm_window') as guard,patch.object(runner,'stage') as effects:
                    with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH|LIMIT_INVALID|SOURCE_MISMATCH'):runner.prepare(file,target)
                    self.assertFalse(target.exists());guard.assert_not_called();effects.assert_not_called()

    def test_invalid_bounds_and_cross_fields_before_output(self):
        # Discovery reference sizes are overridable; array representation
        # overflow remains invalid instead of the former 10000/80000 examples.
        for changes in ({'tenants':2**32},{'replicas':2},{'logical-polling-clients':2**32},
                        {'offered-rps':float('inf')},{'probe-every-ms':0},
                        {'backend-subnet':'10.247.237.0/24'},{'sampler-interval':61},
                        {'diagnostic-resource-profile':a.diagnostic_resources.EXTERNAL_NAME}):
            cfg=config();cfg['prepare'].update(changes)
            with self.subTest(changes=changes),self.assertRaises((RuntimeError,ValueError)):runner.validate_config(cfg)
        cfg=config();cfg['workSeconds']=38
        with self.assertRaisesRegex(RuntimeError,'WORK_WINDOW'):runner.validate_config(cfg)

    def test_remote_realistic_shards_derive_exact_shared_dependency_hashes(self):
        cfg=config();cfg['workSeconds']=3600
        cfg['prepare'].pop('offered-rps')
        cfg['prepare'].update({'tenants':1000,'load-seconds':1800,'logical-polling-clients':100,
                              'sockets-per-tenant':1,'workload-mix':'realistic-v1','workload-scale':2,'driver-shards':8,
                              'pgstream-topology':'external-service-v1',
                              'diagnostic-resource-profile':a.diagnostic_resources.EXTERNAL_NAME,
                              'generator-dependencies':'/synthetic'})
        o=overlay();o['binding']['helperDependencies']={'version':1,'profile':'external-service-batch-v1',
            'files':{name:a.digest(a.ROOT/name) for name in (
                'tools/mt-bench/m7-joined/stream_topology.py',
                'tools/mt-bench/m7-joined/diagnostic_resources.py',
                'tools/mt-bench/m7-joined/experiment_batch.py')}}
        original=copy.deepcopy(o)
        value=rc.remote_projection(cfg,o);bound=value['binding']
        self.assertEqual(o,original)
        self.assertEqual(bound['workload']['cadence']['workloadMix'],'realistic-v1')
        self.assertEqual(bound['workload']['cadence']['workloadScale'],2)
        self.assertEqual(bound['workload']['cadence']['driverShards'],8)
        for name in ('driver_shards.py','contract.py'):
            name='tools/mt-bench/m7-joined/'+name
            self.assertEqual(bound['helperDependencies']['files'][name],a.digest(a.ROOT/name))
        protocol.topology_dependencies(bound,a.ROOT)
        o['binding']['helperDependencies']['files']['tools/mt-bench/m7-joined/driver_shards.py']='0'*64
        with self.assertRaisesRegex(RuntimeError,'M7_CONFIG_REMOTE_SHARD_DEPENDENCY_CHANGED'):rc.remote_projection(cfg,o)
        o=copy.deepcopy(original)
        self.assertEqual(rc.remote_projection(cfg,o),value)

    def test_remote_projection_equivalence_and_actual_consumer(self):
        cfg=config();o=overlay();before=list(sys.path);p=rc.remote_projection(cfg,o);b=p['binding']
        self.assertEqual(sys.path,before)
        self.assertEqual(p,rc.remote_projection(cfg,o))
        self.assertEqual(protocol.prepared_cadence(b),rc.resolve(cfg)['configuration']['cadence'])
        self.assertEqual(protocol.viewer_total(b),4)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=root/'receipt.json';binding=root/'binding.json';run=root/'run.json'
            m,r=packet(cfg);r.update(p['remoteReceiptProjection']);a.write(receipt,r);a.write(binding,b)
            cfg['prepare']['receipt']=str(receipt);a.write(run,cfg)
            argv=['cell.py','prepare','--binding',str(binding),'--cell',str(root/'cell'),'--run-config',str(run)]
            with patch.object(sys,'argv',argv),patch.object(a,'prepare') as prepare,patch.object(cell.app,'record_prepared_binding'):
                cell.main();self.assertEqual(a.cadence_options(prepare.call_args.args[0]),protocol.prepared_cadence(b))
            b['workload']['cadence']['loadSeconds']+=1;a.write(binding,b)
            with patch.object(sys,'argv',argv),patch.object(a,'prepare') as prepare:
                with self.assertRaisesRegex(RuntimeError,'REMOTE_PREPARE_PROFILE_REQUIRED'):cell.main()
                prepare.assert_not_called()
        o['binding']['tenants']=2
        with self.assertRaisesRegex(RuntimeError,'MIRROR_REFUSED'):rc.remote_projection(cfg,o)

    def test_pending_only_ablation_rejects_truthful_accepted_diagnostic(self):
        # Reinstall the original predicate in the actual receipt entrypoint.
        m,r=packet(config())
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'pass.json';a.write(file,{'kind':'joined-acceptance','status':'PASS',
                'pair':m['pair'],'imageId':m['imageId'],'instrument':'a'*64,'evidenceSha256':'b'*64})
            r.update(functionalAcceptanceAtAuthorization='PASS',sourceAcceptance={'status':'PASS','reference':str(file),'sha256':a.digest(file)})
            def criterion(fn):self.assertEqual(fn(m,r,'run')['functionalAcceptance'],'PASS')
            criterion(c.receipt_scope)
            source=inspect.getsource(c.receipt_scope)
            old="(receipt.get('version',1)==2 or receipt.get('functionalAcceptanceAtAuthorization')=='PENDING')"
            self.assertIn(old,source);namespace=dict(c.__dict__)
            exec(compile(source.replace(old,"receipt.get('functionalAcceptanceAtAuthorization')=='PENDING'"),c.__file__,'exec'),namespace)
            with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_RECEIPT_REQUIRED'):criterion(namespace['receipt_scope'])
            criterion(c.receipt_scope)


class Controls(unittest.TestCase):
    setUp=Configuration.setUp
    def test_draft_and_changed_execution_cannot_authorize(self):
        cfg=config();projection=rc.resolve(cfg);m,r=packet(cfg)
        with self.assertRaisesRegex(RuntimeError,'RECEIPT_REQUIRED'):
            c.receipt_scope(m,projection['diagnosticReceiptTemplate'],'run')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a.write(root/'receipt.json',r);cfg['prepare']['receipt']=str(root/'receipt.json')
            cfg['workSeconds']+=1;a.write(root/'run.json',cfg)
            with patch.object(runner,'arm_window') as guard:
                with self.assertRaisesRegex(RuntimeError,'EXECUTION_MISMATCH'):runner.prepare(root/'run.json',root/'never')
                guard.assert_not_called();self.assertFalse((root/'never').exists())

    def test_record_retains_truthful_acceptance_scope(self):
        from profile_provenance import identity,selection
        PROFILE=identity(selection(),
            {'services':{'api':{},'vault':{'command':['vault','server']},'realtime':{},'evaluator':{}}})
        cfg=config();cfg['prepare'].update({'core-commit':'a'*40,'deploy-commit':'b'*40})
        m,r=packet(cfg)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=root/'acceptance.json'
            a.write(evidence,{'kind':'joined-acceptance','status':'PASS','pair':m['pair'],
                'imageId':m['imageId'],'instrument':'a'*64,'evidenceSha256':'b'*64})
            r.update(functionalAcceptanceAtAuthorization='PASS',sourceAcceptance={'status':'PASS','reference':str(evidence),'sha256':a.digest(evidence)})
            scope=c.receipt_scope(m,r,'run');scope.pop('kind')
            m.update(owner='f'*32,hostIdentity='c'*64,profileSelection=PROFILE,
                     settingsFingerprint={'schema':1,'sha256':'f'*64,'sourceCommit':'a'*40,'sourceBlobs':{}},
                     discoveryAuthorization=scope)
            record=discovery.Record(a,root,m);record.value['ownershipVerified']=True;record.save()
            discovery.check_discovery(record.value)
            self.assertEqual(a.document(root/'summary.json')['functionalAcceptance'],'PASS')
            with self.assertRaisesRegex(RuntimeError,'DISCOVERY_NOT_ACCEPTANCE'):c.accepted_claim_scope(record.value)

    def test_configuration_hash_ablation_loses_before_effects_guarantee(self):
        source=inspect.getsource(c.discovery_authorization)
        predicate="isinstance(resolved,dict) and receipt.get('configurationSha256')==sha(resolved)"
        self.assertIn(predicate,source);namespace=dict(c.__dict__)
        exec(compile(source.replace(predicate,'True'),c.__file__,'exec'),namespace)
        with tempfile.TemporaryDirectory() as tmp:
            cfg=config();m,r=packet(cfg);root=Path(tmp);a.write(root/'receipt.json',r)
            cfg['prepare'].update({'receipt':str(root/'receipt.json'),'logical-polling-clients':5})
            a.write(root/'run.json',cfg)
            def criterion():
                target=root/'never-created'
                with patch.object(runner,'arm_window') as guard,patch.object(runner,'stage'):
                    with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH'):runner.prepare(root/'run.json',target)
                    self.assertFalse(target.exists());guard.assert_not_called()
            criterion()
            with patch.object(c,'discovery_authorization',namespace['discovery_authorization']):
                with self.assertRaisesRegex(AssertionError,'RuntimeError not raised'):criterion()
            # The broken path created output: this is a real lost-effect fence.
            self.assertTrue((root/'never-created/config.json').is_file())
            import shutil
            shutil.rmtree(root/'never-created');criterion()

    def test_prepared_resource_mirror_refuses_before_deploy(self):
        cfg=config();cfg['prepare'].update({'diagnostic-resource-profile':a.diagnostic_resources.EXTERNAL_NAME,
            'pgstream-topology':'external-service-v1','generator-dependencies':'/synthetic'})
        m,r=packet(cfg)
        m.update(diagnostics=m['runConfiguration']['diagnostics'],prepared=True,postgresImageId=m['runConfiguration']['postgresImageId'],
                 pgstreamTopology='external-service-v1',diagnosticResources={'profile':a.diagnostic_resources.EXTERNAL_NAME})
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'receipt.json';a.write(receipt,r);m['freeze']=str(receipt)
            a.frozen(m,'deploy')
            m['diagnosticResources']['profile']=a.diagnostic_resources.QUALIFICATION_NAME
            with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH'):a.frozen(m,'deploy')
            m['diagnosticResources']['profile']=a.diagnostic_resources.EXTERNAL_NAME;a.frozen(m,'deploy')

class Namespace(unittest.TestCase):
    def test_actual_daemon_network_projection_refuses_overlap(self):
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):args=parsed(config())
        def run(subnet):
            def command(argv):
                return 'synthetic-id' if argv==['docker','network','ls','-q'] else json.dumps([{'IPAM':{'Config':[{'Subnet':subnet}]}}])
            with patch.object(a,'unused_project_namespace') as names,patch.object(a,'resources',return_value=[]),patch.object(a,'command',side_effect=command):
                result=rc.namespace_preflight(args);names.assert_called_once_with(args.fixture_project);return result
        self.assertEqual(run('10.245.0.0/24')['status'],'PASS')
        with self.assertRaisesRegex(RuntimeError,'LIVE_SUBNET_OVERLAP'):run('10.247.236.0/24')
        self.assertEqual(run('10.245.0.0/24')['status'],'PASS')

if __name__=='__main__':unittest.main()
