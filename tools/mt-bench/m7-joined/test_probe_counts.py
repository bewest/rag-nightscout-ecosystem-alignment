"""Prospective discovery proof; no app, PG, cloud or retained stack actions."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
import discovery as d
from probe import generate

class ProbeCounts(unittest.TestCase):
    def setup(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);folder=Path(tmp.name);out=folder/'load';out.mkdir()
        a.write(folder/'tenants.private.json',[{'id':t} for t in ['a','b','c','d']])
        metrics={'writes_ok':{'count':0},**{'writes_ok{kind:'+k+'}':{'count':0} for k in ('entries','devicestatus','treatments')},**{name+'{tenant:'+t+'}':{'count':0} for t in ('a','b','c','d') for name in ('writes_ok','writes_uncertain')}}
        ledger={'version':2,'kind':'m7-discovery-probe-accounting','runId':'synthetic-loopback','roster':['a','b','c','d'],'admissionsClosed':True,'attempts':4,'byTenant':{t:{'attempts':1,'accepted':int(t=='c'),'uncertain':int(t in ('a','b')),'refused':int(t=='d'),'pending':0} for t in ('a','b','c','d')}}
        return folder,out,metrics,ledger
    def observe(self,folder,out,metrics,ledger,stored):
        if ledger is not None:a.write(out/'probe-accounting.json',ledger)
        with patch.object(a,'stored',return_value=stored) as query:
            result=d.count_observation(a,folder,out,'synthetic-loopback',metrics)
            query.assert_called_once()
            return result
    def test_known_uncertainty_and_legacy_missing_uncertainty(self):
        folder,out,metrics,ledger=self.setup();stored={t:{'probe':1} for t in ('a','b','c')}
        value,known=self.observe(folder,out,metrics,ledger,stored);self.assertTrue(known);self.assertEqual(value['verdict'],'GREEN')
        (out/'probe-accounting.json').unlink();a.write(out/'fanout.json',{'probeWrites':{'byTenant':{'c':1}}})
        value,known=self.observe(folder,out,metrics,None,stored);self.assertFalse(known);self.assertEqual(value['probeCountProof'],'UNMEASURED')
        with self.assertRaisesRegex(RuntimeError,'WRONG_DATA'):self.observe(folder,out,metrics,None,{}) # missing known ACK
    def test_closed_pending_or_open_admissions_remain_unmeasured(self):
        for closed in (False,True):
            folder,out,metrics,ledger=self.setup();ledger['admissionsClosed']=closed;ledger['byTenant']['a'].update(uncertain=0,pending=1)
            value,known=self.observe(folder,out,metrics,ledger,{'a':{'probe':1},'c':{'probe':1}})
            self.assertFalse(known);self.assertEqual(value['verdict'],'UNMEASURED');self.assertEqual(value['probeAccounting']['pending'],1)
    def test_overcount_ack_missing_refused_and_per_tenant_uncertainty_are_hard_and_saved(self):
        cases=[{'a':{'probe':2},'c':{'probe':1}}, {}, {'c':{'probe':1},'d':{'probe':1}}, {'c':{'probe':2}}]
        for stored in cases:
            folder,out,metrics,ledger=self.setup()
            with self.assertRaisesRegex(RuntimeError,'WRONG_DATA') as raised:self.observe(folder,out,metrics,ledger,stored)
            self.assertGreater(raised.exception.oracleFindings['failureCount'],0);self.assertEqual(a.document(out/'oracle-findings.json')['verdict'],'RED');self.assertEqual(a.document(out/'stored-counts.json'),stored)
    def test_metadata_foreign_tampered_negative_wrong_run_or_roster_refuses_before_sql(self):
        changes=[lambda l:l.update(runId='wrong'),lambda l:l.update(attempts=3),lambda l:l.update(admissionsClosed=1),lambda l:l['roster'].append('a'),lambda l:l['byTenant']['a'].update(uncertain=-1),lambda l:l['byTenant'].update(foreign=l['byTenant']['a']),lambda l:l['byTenant']['a'].update(accepted=1)]
        for change in changes:
            folder,out,metrics,ledger=self.setup();change(ledger);a.write(out/'probe-accounting.json',ledger)
            with patch.object(a,'stored') as query:
                with self.assertRaisesRegex(RuntimeError,'PROBE_COUNTS'):d.count_observation(a,folder,out,'synthetic-loopback',metrics)
                query.assert_not_called();self.assertEqual(a.document(out/'oracle-findings.json')['verdict'],'RED')
        folder,out,metrics,ledger=self.setup();a.write(out/'probe-accounting.json',ledger);a.write(out/'fanout.json',{'probeWrites':{'byTenant':{'a':1}}})
        with patch.object(a,'stored') as query:
            with self.assertRaisesRegex(RuntimeError,'ACK_MISMATCH'):d.count_observation(a,folder,out,'synthetic-loopback',metrics)
            query.assert_not_called()
    def test_foreign_stored_workload_wrong_count_and_missing_metadata_are_not_zero(self):
        folder,out,metrics,ledger=self.setup()
        with self.assertRaisesRegex(RuntimeError,'TENANT_SCOPE'):self.observe(folder,out,metrics,ledger,{'foreign':{'probe':1}})
        with self.assertRaisesRegex(RuntimeError,'WRONG_DATA'):self.observe(folder,out,metrics,ledger,{'a':{'entries':1},'c':{'probe':1}})
        value,known=self.observe(folder,out,{},ledger,{'c':{'probe':1}});self.assertFalse(known);self.assertGreater(value['missingFieldCount'],0)
    def test_missing_actual_count_field_is_unmeasured_never_fabricated_zero(self):
        for key in ('writes_ok','writes_ok{tenant:a}','writes_uncertain{tenant:a}','writes_ok{kind:entries}'):
            for row in ({},{'values':{}},{'rate':0},{'values':{'rate':0}}):
                folder,out,metrics,ledger=self.setup();metrics[key]=row
                value,known=self.observe(folder,out,metrics,ledger,{'c':{'probe':1}})
                self.assertFalse(known);self.assertEqual(value['verdict'],'UNMEASURED');self.assertIn(key,value['missingFields'])
                if key=='writes_ok{tenant:a}':self.assertIsNone(next(r for r in value['rows'] if r['tenant']=='a')['accepted'])
    def test_invalid_actual_counter_refuses_before_query_nested_or_flat(self):
        for key in ('writes_ok','writes_ok{tenant:a}','writes_uncertain{tenant:a}','writes_ok{kind:entries}'):
            for value in (True,False,1.5,float('inf'),float('-inf'),float('nan'),-1,'0',None,9007199254740992):
                for nested in (False,True):
                    folder,out,metrics,ledger=self.setup();metrics[key]={'values':{'count':value}} if nested else {'count':value};a.write(out/'probe-accounting.json',ledger)
                    with patch.object(a,'stored') as query:
                        with self.assertRaisesRegex(RuntimeError,'COUNTER_INVALID'):d.count_observation(a,folder,out,'synthetic-loopback',metrics)
                        query.assert_not_called();self.assertEqual(a.document(out/'oracle-findings.json')['verdict'],'RED')
        for row in (None,1,{'values':None},{'values':[]},{'values':'invalid'}):
            folder,out,metrics,ledger=self.setup();metrics['writes_ok']=row;a.write(out/'probe-accounting.json',ledger)
            with patch.object(a,'stored') as query:
                with self.assertRaisesRegex(RuntimeError,'COUNTER_INVALID'):d.count_observation(a,folder,out,'synthetic-loopback',metrics)
                query.assert_not_called()
    def test_valid_nested_and_integral_numeric_counter_preserved(self):
        folder,out,metrics,ledger=self.setup();metrics={key:{'values':{'count':float(row['count'])}} for key,row in metrics.items()}
        value,known=self.observe(folder,out,metrics,ledger,{'c':{'probe':1}});self.assertTrue(known);self.assertEqual(value['verdict'],'GREEN')
    def test_real_loopback_actual_generated_request_callback(self):
        folder,out,metrics,_=self.setup();file=folder/'probe.js';generate(a.ROOT,file)
        proc=subprocess.run(['node',str(a.HERE/'probe-accounting-control.cjs'),str(file)],capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr);value=json.loads(proc.stdout);self.assertEqual(value['statuses'],[503,0,200,403])
        result,known=self.observe(folder,out,metrics,value['ledger'],{t:{'probe':n} for t,n in value['stored'].items()});self.assertTrue(known);self.assertEqual(result['verdict'],'GREEN')
    def test_default_acceptance_oracle_remains_exact(self):
        # Strict/default contract has no new ambiguity allowance for probes.
        from contract import oracle
        self.assertEqual(oracle({'a':{'probe':1}},{},{},[{'id':'a'}],allow_empty=True)['verdict'],'RED')

if __name__=='__main__':unittest.main()
