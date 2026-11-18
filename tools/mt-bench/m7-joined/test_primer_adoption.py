import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
import primer_options
from test_run_configuration import config as runner_config, packet

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
C='33333333-3333-4333-8333-333333333333'
class PrimerAdoption(unittest.TestCase):
    def test_authored_primer_options_are_bound_before_deploy(self):
        configuration=runner_config()
        configuration['prepare'].update({'primer-concurrency':64,'primer-max-tenants':20000})
        with patch.object(adapter,'instrument',return_value={'sha256':'d'*64}):
            manifest, receipt=packet(configuration)
        self.assertEqual(primer_options.from_manifest(manifest),{'concurrency':64,'maxTenants':20000})
        from contract import discovery_authorization
        discovery_authorization(manifest,receipt)
        legacy={key:value for key,value in receipt.items() if key!='version'}
        with self.assertRaisesRegex(RuntimeError,'PRIMER_OPTIONS_BOUND_RECEIPT_REQUIRED'):
            discovery_authorization(manifest,legacy)
        for field,value in [('primerConcurrency',33),('primerMaxTenants',10001)]:
            with self.assertRaisesRegex(RuntimeError,'DIAGNOSTIC_CONFIGURATION_MISMATCH'):
                discovery_authorization({**manifest,field:value},receipt)
        discovery_authorization(manifest,receipt)

    def test_image_preflight_refuses_legacy_source_before_image_access(self):
        from types import SimpleNamespace
        args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',primer_concurrency=33,
                             deploy_repo='/synthetic/deploy',deploy_commit='f'*40)
        with patch.object(adapter,'command',return_value=b'legacy native primer') as command, patch.object(adapter,'image') as image:
            with self.assertRaisesRegex(RuntimeError,'PRIMER_OPTION_SOURCE_UNSUPPORTED'):
                adapter.prepare_image_inputs(args)
            image.assert_not_called()
            command.assert_called_once_with(['git','-C',args.deploy_repo,'show',args.deploy_commit+':'+primer_options.SOURCE_PATH],binary=True)

    def test_extended_source_constructor_precedes_unbound_resource_driver(self):
        from types import SimpleNamespace
        args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',primer_concurrency=64,
                             primer_max_tenants=20000,deploy_repo='/synthetic/deploy',deploy_commit='f'*40,
                             generator_dependencies='/synthetic/dependencies')
        proof={'primerSource':{'protocol':primer_options.PROTOCOL}}
        class DriverWouldArm(Exception):pass
        with patch.object(adapter,'selected_resources_profile',return_value='selected'), \
             patch.object(adapter,'commit') as commit, patch.object(adapter,'prepare_image_inputs',return_value=proof) as preflight, \
             patch.object(adapter.diagnostic_resources,'configure',side_effect=DriverWouldArm) as configure:
            with self.assertRaises(DriverWouldArm):adapter.prepare(args)
        configure.assert_called_once_with('selected')
        commit.assert_called_once_with(args.deploy_repo,args.deploy_commit)
        preflight.assert_called_once_with(args)
        self.assertEqual(args.image_input_preflight,proof)

    def test_timed_out_constructor_removes_exact_owned_container_and_checks_absence(self):
        name='ns-primer-option-probe-'+'a'*32
        container='b'*64
        image='sha256:'+'c'*64
        events=[]
        for cleanup in ('owned','foreign','unobservable'):
            with self.subTest(cleanup=cleanup):
                state={'present':False}
                events.clear()

                def docker(argv, timeout):
                    self.assertGreater(timeout,0)
                    self.assertEqual(argv[:2],['docker','container'])
                    action=argv[2]
                    events.append(action)
                    if action=='create':
                        self.assertEqual(argv[argv.index('--name')+1],name)
                        self.assertIn('org.nightscout.m7.owner='+'a'*32,argv)
                        self.assertIn(primer_options._PROBE_LABEL+'=v1',argv)
                        self.assertEqual(argv[argv.index('--network')+1],'none')
                        self.assertEqual(argv[argv.index('--pull')+1],'never')
                        self.assertIn('--read-only',argv)
                        self.assertIn('--init',argv)
                        self.assertIn('--cpus',argv)
                        self.assertIn('--memory-swap',argv)
                        self.assertIn('--pids-limit',argv)
                        state['present']=True
                        return container+'\n'
                    if action=='ls':
                        if cleanup=='unobservable' and 'start' in events:
                            raise subprocess.CalledProcessError(1,argv)
                        return container+'\n' if state['present'] else ''
                    if action=='inspect':
                        owner='d'*32 if cleanup=='foreign' and 'start' in events else 'a'*32
                        return json.dumps([container,'/'+name,image,owner,'v1'])
                    if action=='start':
                        self.assertEqual(argv[3:],['--attach',container])
                        raise subprocess.TimeoutExpired(argv,timeout)
                    if action=='rm':
                        self.assertEqual(argv[3:],['--force',container])
                        state['present']=False
                        return container
                    self.fail('Unexpected Docker operation '+action)

                with patch.object(primer_options.uuid,'uuid4',return_value=primer_options.uuid.UUID(hex='a'*32)):
                    code={'owned':'PRIMER_OPTION_PROBE_TIMEOUT','foreign':'PRIMER_OPTION_PROBE_OWNER_CHANGED',
                          'unobservable':'PRIMER_OPTION_PROBE_CLEANUP_UNMEASURED'}[cleanup]
                    with self.assertRaisesRegex(RuntimeError,code):
                        primer_options.probe_image(docker,image,primer_options._DECLARATION,{'concurrency':64},adapter.primer_need)
                self.assertEqual(events[:4],['create','ls','inspect','start'])
                self.assertEqual(('rm' in events,state['present']),(cleanup=='owned',cleanup!='owned'))
                if cleanup=='owned':self.assertEqual(events[-3:],['rm','ls','ls'])

    def fixture(self,root):
        adapter.write(root/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':'synthetic_application'}}}})
        p=root/'state/primer'
        for name,value in {
            'config.json':{'seed':[{'id':A},{'id':B}]},
            'provisioned.json':[{'id':A},{'id':B}],
            'tenants.json':{'version':1,'tenants':[{'id':i,'host':h,'dataToken':'synthetic-data'} for i,h in [(A,'a.example.test'),(B,'b.example.test')]]},
            'primed.json':{'state':'synthetic-data-primed','tenants':2},
            'entry-requests.json':{'version':1,'tenants':{}}
        }.items():adapter.write(p/name,value)
    def test_only_prime_gets_bound_option_default_keeps_existing_argv(self):
        config={'services':{'api':{'command':['node','api']},'evaluator':{'command':['node','evaluator']}}}
        serial=adapter.deployment_plan(config,True)
        for workers in (1,2,4,32,33,64):
            concurrent=adapter.deployment_plan(config,True,workers)
            for old,new in zip(serial,concurrent):
                self.assertEqual(old[:2],new[:2])
                self.assertEqual(new[2],old[2]+(['--concurrency',str(workers)] if old[0]=='prime' and workers!=1 else []))
        for maximum in (10001,20000):
            limited=adapter.deployment_plan(config,True,64,primer_max_tenants=maximum)
            for old,new in zip(serial,limited):
                self.assertEqual(new[2],old[2]+(['--concurrency','64','--max-tenants',str(maximum)] if old[0]=='prime' else []))
        for value in (0,2**53,True,'4',2.5):
            with self.assertRaisesRegex(RuntimeError,'PRIMER_CONCURRENCY_INVALID'):adapter.deployment_plan(config,True,value)
            with self.assertRaisesRegex(RuntimeError,'PRIMER_MAX_TENANTS_INVALID'):adapter.deployment_plan(config,True,primer_max_tenants=value)
    def test_database_count_catches_missing_duplicate_and_foreign_tenants_then_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            good=f'{A}\t1\n{B}\t1\n'
            for raw in (f'{A}\t1\n',f'{A}\t2\n{B}\t1\n',f'{A}\t1\n{C}\t1\n'):
                with patch.object(adapter,'psql',return_value=raw) as sql:
                    with self.assertRaisesRegex(RuntimeError,'DATABASE_COUNT_MISMATCH'):adapter.primer_counts(root,{'tenants':2})
                    self.assertEqual(adapter.document(root/'primer-counts.private.json')['verdict'],'FAIL')
                    self.assertIn("doc->>'device'='synthetic-compose-demo'",sql.call_args.args[1])
            with patch.object(adapter,'psql',return_value=good):
                result=adapter.primer_counts(root,{'tenants':2})
            self.assertEqual(result['verdict'],'PASS');self.assertEqual(result['persistedEntries'],2)
            self.assertEqual((root/'primer-counts.private.json').stat().st_mode&0o777,0o600)
    def test_seed_custody_and_uncertainty_mismatch_refuse_before_sql(self):
        for name,value,code in [
            ('config.json',{'seed':[{'id':A},{'id':A}]},'SEED_COUNT'),
            ('provisioned.json',[{'id':A},{'id':C}],'CUSTODY_COUNT'),
            ('primed.json',{'state':'synthetic-data-primed','tenants':1},'CUSTODY_COUNT'),
            ('entry-requests.json',{'version':1,'tenants':{A:{'state':'outcome-uncertain'}}},'ENTRY_UNCERTAIN')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root);adapter.write(root/'state/primer'/name,value)
                with patch.object(adapter,'psql') as sql:
                    with self.assertRaisesRegex(RuntimeError,code):adapter.primer_counts(root,{'tenants':2})
                    sql.assert_not_called()
    def test_actual_psql_argv_selects_frozen_application_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with patch.object(adapter,'compose',return_value=f'{A}\t1\n{B}\t1\n') as call:
                self.assertEqual(adapter.primer_counts(root,{'tenants':2})['verdict'],'PASS')
                args=call.call_args.args
                self.assertEqual(args[args.index('-d')+1],'synthetic_application')
            for value in (None,'', 'postgres --bad', {'database':'wrong'}):
                adapter.write(root/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':value}}}})
                with patch.object(adapter,'compose') as call:
                    with self.assertRaisesRegex(RuntimeError,'APPLICATION_DATABASE_REQUIRED'):adapter.primer_counts(root,{'tenants':2})
                    call.assert_not_called()
    def test_higher_point_exact_roster_counts_without_runtime(self):
        for n in (3000,5000,10000):
            with self.subTest(tenants=n),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root);p=root/'state/primer';ids=[str(__import__('uuid').UUID(int=i+1)) for i in range(n)]
                adapter.write(p/'config.json',{'seed':[{'id':i} for i in ids]})
                adapter.write(p/'provisioned.json',[{'id':i} for i in ids])
                adapter.write(p/'tenants.json',{'version':1,'tenants':[{'id':i,'host':'t'+str(k)+'.example.test','dataToken':'synthetic'} for k,i in enumerate(ids)]})
                adapter.write(p/'primed.json',{'state':'synthetic-data-primed','tenants':n})
                with patch.object(adapter,'psql',return_value=''.join(i+'\t1\n' for i in ids)):
                    self.assertEqual(adapter.primer_counts(root,{'tenants':n})['persistedTenants'],n)
if __name__=='__main__':unittest.main()
