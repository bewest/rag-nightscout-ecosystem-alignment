"""Sparse discovery uses the actual count observer and corruption controller.

SQL effects are synthetic; no database/captured point or application campaign.
"""
import copy
import contextlib
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
import discovery as d
from discovery_counts import observe, control_domain
import profile_provenance


class SparseControl(unittest.TestCase):
    def fixture(self,domain='entries',size=1000):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);out=root/'load';out.mkdir()
        ids=['tenant-'+str(i) for i in range(size)]
        m={'pair':{'core':'a'*40,'deploy':'b'*40},'instrument':{'sha256':'d'*64},
           'profile':'pgstream-sample','runPurpose':'discovery','owner':'f'*32,'tenants':size,'replicas':1,
           'generator':{},'hostIdentity':'c'*64,'imageId':'sha256:'+'e'*64,'cadence':{'loadSeconds':180,'idleSeconds':1,'warmupSeconds':1},
           'settingsFingerprint':{'schema':1,'sha256':'f'*64,'sourceCommit':'a'*40,'sourceBlobs':{}}}
        m['profileSelection']=profile_provenance.identity(profile_provenance.selection(),
            {'services':{'api':{},'vault':{'command':['vault','server']},'realtime':{},'evaluator':{}}})
        a.write(root/'owner.json',m);a.write(root/'tenants.private.json',[{'id':t} for t in ids]);(out/'runid').write_text('synthetic-sparse')
        metrics={'writes_ok':{'count':345},**{'writes_ok{kind:'+k+'}':{'count':345 if k==domain else 0} for k in ('entries','devicestatus','treatments')}}
        for t in ids:
            metrics['writes_ok{tenant:'+t+'}']={'count':345 if t==ids[0] else 0}
            metrics['writes_uncertain{tenant:'+t+'}']={'count':0}
        a.write(out/'k6-summary.json',{'metrics':metrics});a.write(out/'fanout.json',{'probeWrites':{'byTenant':{}}})
        ledger={'version':2,'kind':'m7-discovery-probe-accounting','runId':'synthetic-sparse','roster':ids,
                'admissionsClosed':True,'attempts':0,'byTenant':{}}
        a.write(out/'probe-accounting.json',ledger)
        state={ids[0]:{domain:345}};sql=[]
        def psql(directory,statement,database):
            self.assertEqual(database,'nightscout_compose_test');sql.append(statement)
            self.assertIn('nsdemo_'+domain+'.'+domain,statement)
            field='enteredBy' if domain=='treatments' else 'device'
            self.assertIn("doc->>'"+field+"'",statement)
            self.assertIn("current_setting('app.current_tenant_id')::uuid",statement)
            self.assertIn("RETURNING 'm7-count-control-victim'",statement)
            restore="to_jsonb('synthetic-sparse'::text)" in statement
            state[ids[0]][domain]+=1 if restore else -1
            return ids[0]+'\nm7-count-control-victim\n'
        return root,m,metrics,state,sql,psql

    @contextlib.contextmanager
    def runtime(self,state,psql):
        with patch.object(a,'stored',side_effect=lambda *_:copy.deepcopy(state)),patch.object(a,'assert_owned'),patch.object(a,'verify'),patch.object(a,'psql',side_effect=psql):yield

    def test_actual_discovery_control_sparse_cohort_and_all_ordinary_domains(self):
        for domain in ('entries','devicestatus','treatments'):
            with self.subTest(domain=domain):
                root,m,metrics,state,sql,psql=self.fixture(domain)
                with self.runtime(state,psql):a.control(root,m)
                self.assertEqual(a.document(root/'load/oracle-control.json'),{'baseline':'GREEN','broken':'RED','restored':'GREEN'})
                broken=a.document(root/'load/oracle-control-broken.json')
                self.assertEqual(broken['code'],'M7_DISCOVERY_WRONG_DATA');self.assertGreater(broken['failureCount'],0)
                self.assertEqual(state['tenant-0'][domain],345);self.assertEqual(len(sql),2)

    def test_missing_uncertain_inexact_or_empty_witness_refuses_before_mutation(self):
        for case in ('missing','ordinary-uncertain','probe-uncertain','pending','empty','wrong-count'):
            root,m,metrics,state,sql,psql=self.fixture(size=3);out=root/'load'
            if case=='missing':del metrics['writes_ok{tenant:tenant-1}']
            if case=='ordinary-uncertain':metrics['writes_uncertain{tenant:tenant-1}']={'count':1}
            if case in ('probe-uncertain','pending'):
                ledger=a.document(out/'probe-accounting.json');ledger['attempts']=1
                ledger['byTenant']={'tenant-1':{'attempts':1,'accepted':0,'uncertain':int(case=='probe-uncertain'),'pending':int(case=='pending'),'refused':0}}
                a.write(out/'probe-accounting.json',ledger)
            if case=='empty':
                state.clear()
                for row in metrics.values():row['count']=0
            if case=='wrong-count':state['tenant-0']['entries']+=1
            a.write(out/'k6-summary.json',{'metrics':metrics})
            with self.runtime(state,psql):
                with self.assertRaisesRegex(RuntimeError,'BASELINE_NOT_EXACT'):a.control(root,m)
            self.assertEqual(sql,[]);self.assertFalse((out/'oracle-control.json').exists())

    def test_noop_corruption_is_vacuous_and_restoration_failure_never_passes(self):
        for mode in ('noop','omit-restore','no-victim'):
            root,m,metrics,state,sql,psql=self.fixture(size=3)
            def altered(directory,statement,database):
                if mode=='noop':sql.append(statement);return 'm7-count-control-victim\n'
                if mode=='no-victim':sql.append(statement);return ''
                if "to_jsonb('synthetic-sparse'::text)" in statement:
                    sql.append(statement);return ''
                return psql(directory,statement,database)
            with self.runtime(state,altered):
                with self.assertRaisesRegex(RuntimeError,{'noop':'DID_NOT_FAIL','omit-restore':'NOT_RESTORED','no-victim':'NO_VICTIM'}[mode]):a.control(root,m)
            self.assertEqual(len(sql),2);self.assertFalse((root/'load/oracle-control.json').exists())
        # Restored real effects pass again through the same controller.
        root,m,_,state,_,psql=self.fixture(size=3)
        with self.runtime(state,psql):a.control(root,m)
        self.assertEqual(a.document(root/'load/oracle-control.json')['restored'],'GREEN')

    def test_default_strict_oracle_still_refuses_sparse_cohort(self):
        root,m,_,state,sql,psql=self.fixture(size=3)
        with self.runtime(state,psql):
            with self.assertRaisesRegex(RuntimeError,'BASELINE_NOT_GREEN'):a.oracle_control(root)
        self.assertEqual(sql,[])

    def run_collection(self,runner):
        root,m,metrics,state,sql,psql=self.fixture(size=3);a.write(root/'deploy-before-host.json',{})
        def load(*args,**kwargs):
            record=args[4]
            counted,known=observe(a,root,root/'load','synthetic-sparse',metrics);self.assertTrue(known)
            record.value.update(oracle=counted,probe={'completedOutput':{'verdict':'PASS'}},
                settingsFingerprintObservation={'verdict':'PASS'},processes={'k6':{'returncode':0},'probe':{'returncode':0}})
        with self.runtime(state,psql),contextlib.ExitStack() as stack:
            for name in ('frozen','quiet','image','verify_generator','readiness','phase_snapshot','enabled_idle'):stack.enter_context(patch.object(a,name))
            # No runtime stages or SQL resets: the actual control alone uses psql.
            original=a.psql
            stack.enter_context(patch.object(a,'psql',side_effect=lambda folder,query,*args:original(folder,query,*args) if query.startswith('BEGIN;') else ''))
            stack.enter_context(patch.object(a.time,'sleep'))
            stack.enter_context(patch.object(a,'command',return_value='[{"Id":"synthetic"}]'))
            stack.enter_context(patch.object(a,'sample_preflight',return_value=({},{})))
            stack.enter_context(patch.object(a,'sample_results',return_value={'scope':'synthetic'}))
            stack.enter_context(patch.object(d,'discovery_load',side_effect=load))
            stack.enter_context(patch.dict(runner.__globals__,{'discovery_load':load}))
            stack.enter_context(patch('reduce.measurements',return_value={'complete':True}))
            return runner(a,root,m,'synthetic-k6'),sql

    def test_actual_collection_routes_sparse_control_and_old_predicate_is_red(self):
        result,sql=self.run_collection(d.run_discovery)
        self.assertEqual(result['oracleControl'],{'baseline':'GREEN','broken':'RED','restored':'GREEN'});self.assertEqual(len(sql),2)
        # Resource admission now wraps the collector. Ablate the predicate
        # in the actual collector rather than the delegation-only wrapper.
        source=inspect.getsource(d._run_discovery)
        needle="control_domain(counts,m['tenants']) is not None"
        self.assertIn(needle,source);namespace=dict(d.__dict__)
        old="counts and counts.get('rows') and all(row.get('accepted',0)>0 and row.get('uncertain',0)==0 for row in counts['rows'])"
        exec(compile(source.replace(needle,old),d.__file__,'exec'),namespace)
        broken,sql=self.run_collection(namespace['_run_discovery'])
        self.assertNotIn('oracleControl',broken);self.assertEqual(sql,[])
        self.assertEqual(broken['strictChecks']['oracleControl']['code'],'M7_DISCOVERY_COUNTS_MISSING')
        restored,sql=self.run_collection(d.run_discovery);self.assertIn('oracleControl',restored);self.assertEqual(len(sql),2)

if __name__=='__main__':unittest.main()
