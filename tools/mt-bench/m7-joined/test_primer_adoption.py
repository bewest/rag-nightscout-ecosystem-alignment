import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
C='33333333-3333-4333-8333-333333333333'
class PrimerAdoption(unittest.TestCase):
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
        for workers in (2,4):
            concurrent=adapter.deployment_plan(config,True,workers)
            for old,new in zip(serial,concurrent):
                self.assertEqual(old[:2],new[:2])
                self.assertEqual(new[2],old[2]+(['--concurrency',str(workers)] if old[0]=='prime' else []))
        for value in (0,33,True,'4',2.5):
            with self.assertRaisesRegex(RuntimeError,'PRIMER_CONCURRENCY_INVALID'):adapter.deployment_plan(config,True,value)
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
