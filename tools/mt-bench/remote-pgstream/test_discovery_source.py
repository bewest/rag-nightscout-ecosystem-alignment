"""Discovery requests never substitute for source/image/authorization admission."""
import copy,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app,cell,protocol,transport
import test_discovery_reporting as reporting

class DiscoverySource(unittest.TestCase):
    def request(self):
        b=reporting.DiscoveryReporting().selected(7)
        b.update(pair={'core':'a'*40,'deploy':'b'*40},imageId='sha256:'+'c'*64)
        return b

    def test_config_only_generic_source_is_request_strict_stays_closed(self):
        b=self.request();self.assertEqual(protocol.binding(b),b)
        with self.assertRaisesRegex(RuntimeError,'QUALIFIED_SOURCE'):
            transport.qualified_source(b['pair'],b['imageId'])
        m=dict(pair=b['pair'],imageId=b['imageId'],postgresImageId=transport.POSTGRES,tenants=b['tenants'],replicas=1,
               profile='pgstream-sample',runPurpose='discovery',measurementMode='accepted',completionContract='evaluator-work-v2',
               cadence=b['workload']['cadence'],primerConcurrency=b['workload']['primerConcurrency'])
        transport.cell_contract(m,b)
        for mutate in (lambda b:b.update(reportMode='strict'),lambda b:b.update(expiresAt=0),
                       lambda b:b['pair'].update(core='abc'),lambda b:b.update(imageId='tag'),
                       lambda b:b['workload']['cadence'].update(offeredRps=0)):
            bad=copy.deepcopy(b);mutate(bad)
            with self.assertRaises(RuntimeError):protocol.binding(bad)

    def test_actual_helper_parser_binds_configured_pair_before_prepare(self):
        b=self.request()
        with tempfile.TemporaryDirectory() as root:
            args=reporting.DiscoveryReporting().args(b,root)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
                cell.main();parsed=prepare.call_args.args[0]
                self.assertEqual(parsed.core_commit,b['pair']['core']);self.assertEqual(parsed.deploy_commit,b['pair']['deploy'])
                self.assertEqual(parsed.image,b['imageId'])
            receipt=Path(root)/'receipt.json';saved=receipt.read_text();bad=json.loads(saved);bad['remoteWorkload']['cadence']['offeredRps']=99;receipt.write_text(json.dumps(bad))
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare:
                with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION_REQUIRED'):cell.main()
                prepare.assert_not_called()
            receipt.write_text(saved)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
                cell.main();prepare.assert_called_once()

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_SOURCE_CONFIG'),'exact source/dependency configuration required')
    def test_actual_paired_git_archives_loaders_break_restore(self):
        config=json.loads(Path(os.environ['REMOTE_PGSTREAM_SOURCE_CONFIG']).read_text())
        core,deploy=config['coreRepository'],config['deployRepository'];a=app.a
        with tempfile.TemporaryDirectory() as root:
            d=Path(root);(d/'dependencies').mkdir();(d/'dependencies/node_modules').symlink_to(config['dependencies'],target_is_directory=True)
            for pair in config['pairs']:
                a.commit(core,pair['core']);a.commit(deploy,pair['deploy']);a.discovery_source_features(core,pair['core'])
                result=a.discovery_source_contract(d,{'pair':pair,'replicas':1},core,deploy)
                self.assertTrue(result['ok']);self.assertTrue(result['processes'])
            m={'pair':config['pairs'][0],'replicas':1};command=a.command
            def broken(argv,**kwargs):
                value=command(argv,**kwargs)
                if len(argv)>1 and str(argv[1]).endswith('prospective-plan-documents.js'):
                    docs=json.loads(value);docs['processes'][0]['files']={};return json.dumps(docs)
                return value
            with patch.object(a,'command',side_effect=broken):
                with self.assertRaisesRegex(RuntimeError,'M7_COMMAND_FAILED:node'):a.discovery_source_contract(d,m,core,deploy)
            self.assertTrue(a.discovery_source_contract(d,m,core,deploy)['ok'])
            with self.assertRaises(RuntimeError):a.commit(core,'f'*40)
            with self.assertRaises(RuntimeError):a.discovery_source_contract(d,{'pair':config['incompatiblePair'],'replicas':1},core,deploy)

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired controller checkout required')
    def test_actual_caller_worker_helper_chain(self):
        controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT']).resolve()
        spec=importlib.util.spec_from_file_location('admission_controller_worker',controller/'tools/perf-cloud/pgstream-worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        for tenants,rate,duration,clients,total in ((2,13,23,1,2),(37,73,45,3,111),(37,73,45,3,2),(37,73,45,3,0),(37,73,45,3,53)):
            b=self.request();b['tenants']=tenants
            b['workload']['cadence'].update(offeredRps=rate,loadSeconds=duration,socketsPerTenant=clients)
            b['workload']['resourcePlan'].update(tenants=tenants,logicalPollingClients=total)
            hosts={role:{**value,'privateIPv4':b['appAddress'] if role=='sut' else b['generatorAddress']} for role,value in b['workload']['resourcePlan']['hosts'].items()}
            selected={'profile':b['profile'],'reportMode':'discovery','runId':b['runId'],'cloudId':b['cloudId'],'nonce':b['nonce'],
                      'tenants':tenants,'pins':{**b['pair'],'app':b['imageId'],'postgres':transport.POSTGRES},'cadence':b['workload']['cadence'],
                      'primerConcurrency':b['workload']['primerConcurrency'],'resourcePlan':b['workload']['resourcePlan'],'hosts':hosts,
                      'port':b['port'],'expiresAt':b['expiresAt'],'k6Image':b['k6Image'],'extensionSha256':b['sourceSha256'],
                      'transport':b['transport'],'completionContract':'evaluator-work-v2','diagnostics':'off'}
            script="import {runtimeBinding} from "+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+";let s='';for await(const c of process.stdin)s+=c;console.log(JSON.stringify(runtimeBinding(JSON.parse(s))));"
            bound=json.loads(subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(selected),capture_output=True,text=True,check=True).stdout)
            self.assertEqual(bound,b);protocol.binding(bound)
            with tempfile.TemporaryDirectory() as root:
                d=Path(root);(d/'input').mkdir()
                (d/'input/binding.json').write_text(json.dumps(bound))
                receipt={'status':'AUTHORIZED_DIAGNOSTIC','remoteProfile':b['profile'],'remoteTransport':b['transport'],
                         'remoteExtensionSha256':b['sourceSha256'],'completionContract':'evaluator-work-v2',
                         'remoteWorkload':b['workload'],'remoteReportMode':'discovery'}
                (d/'input/receipt.json').write_text(json.dumps(receipt))
                with patch.object(worker,'ROOT',d):args=worker.prepare_arguments(selected)
                with patch.object(sys,'argv',['cell.py',*map(str,args[2:])]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
                    cell.main();parsed=prepare.call_args.args[0]
                    self.assertEqual(app.a.cadence_options(parsed),protocol.prepared_cadence(b));self.assertEqual(parsed.tenants,tenants)
                    self.assertEqual(parsed.core_commit,b['pair']['core']);self.assertEqual(parsed.image,b['imageId'])
                    # Actual canonical worker omits the optional knob. The shared
                    # prepare selection must still choose discovery's durable observer.
                    self.assertIsNone(parsed.evaluator_opportunities)
                    manifest={'runPurpose':'discovery','profile':parsed.profile,'completionContract':parsed.completion_contract}
                    app.a.select_opportunities(parsed,manifest)
                    self.assertEqual(manifest['evaluatorOpportunities'],'received-input-v1')
                    strict={**manifest,'runPurpose':'acceptance'};strict.pop('evaluatorOpportunities')
                    app.a.select_opportunities(parsed,strict);self.assertNotIn('evaluatorOpportunities',strict)

    def test_independent_totals_and_local_explicit_zero_admission(self):
        for total in (0,2,53,80000):
            b=self.request();b['workload']['resourcePlan']['logicalPollingClients']=total
            protocol.binding(b);self.assertEqual(protocol.viewer_total(b),total)
            with tempfile.TemporaryDirectory() as tmp:
                cli=reporting.DiscoveryReporting().args(b,tmp)
                parsed=app.a.parser().parse_args(['prepare','--directory','/synthetic',*cli[cli.index('--core-repo'):],'--logical-polling-clients',str(total)])
            self.assertEqual(app.a.cadence_options(parsed)['logicalPollingClients'],total)
        for total in (-1,80001,True,1.5):
            b=self.request();b['workload']['resourcePlan']['logicalPollingClients']=total
            with self.assertRaises(RuntimeError):protocol.binding(b)

    def test_admission_failure_blocks_ingress_and_export_before_effects(self):
        # Exercise actual app.load ordering, keeping all host ports synthetic.
        b=self.request();m=dict(pair=b['pair'],imageId=b['imageId'],freeze='synthetic',tenants=b['tenants'],replicas=1)
        receipt={'remoteReportMode':'discovery','remoteWorkload':b['workload'],'remoteProfile':b['profile'],
                 'remoteTransport':b['transport'],'remoteExtensionSha256':b['sourceSha256']}
        with patch.object(app.a,'load',return_value=(Path('/synthetic-cell'),m)),patch('host_binding.preflight'),patch('transport.cell_contract'),\
             patch.object(app.a,'frozen'),patch.object(app.a,'document',return_value=receipt),patch.object(app.a,'image',return_value=b['imageId']),\
             patch.object(app,'source_identity',return_value={'sha256':b['sourceSha256']}),\
             patch.object(app.a,'discovery_source_preflight',side_effect=RuntimeError('M7_DISCOVERY_SOURCE_CONTRACT_REFUSED')) as check,\
             patch.object(app,'write') as write,patch('transport.local_nics') as nics:
            for action in (app.ingress,app.export_traffic):
                with self.assertRaisesRegex(RuntimeError,'SOURCE_CONTRACT_REFUSED'):action('/synthetic-cell',b)
            self.assertEqual(check.call_count,2);write.assert_not_called();nics.assert_not_called()

if __name__=='__main__':unittest.main()
