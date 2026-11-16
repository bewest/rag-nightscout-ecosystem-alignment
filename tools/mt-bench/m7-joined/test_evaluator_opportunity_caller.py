"""Actual private caller/reader/Observer with injected SQL and RPC boundaries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import adapter as a
import evaluator_progress as p
import evaluator_opportunities as o
import evaluator_idle as idle
import test_evaluator_progress as fixtures
from test_evaluator_progress import A,B
from test_evaluator_opportunities import BINDING

NODE=Path(os.environ.get('NODE_BINARY','/home/bewest/n/n/versions/node/24.22.1/bin/node'))


@unittest.skipUnless(NODE.is_file(),'actual qualified Node source reader required')
class Caller(unittest.TestCase):
    def fixture(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);d=Path(temporary.name);out=d/'load';out.mkdir()
        binding=copy.deepcopy(BINDING)
        config={'clock':'synthetic_clock','checkpoint':'synthetic_checkpoint','entries':'synthetic_entries','consumer':'evaluator-sample-completed','kind':'evaluator-work-v2','binding':binding}
        a.write(d/'completion-source.json',config);a.write(d/'tenants.private.json',[{'id':A},{'id':B}])
        a.write(d/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':'synthetic_test'}}}})
        m={'profile':'pgstream-sample','completionContract':'evaluator-work-v2','runPurpose':'discovery','evaluatorOpportunities':o.CONTRACT,
           'pair':binding['pair'],'imageId':binding['imageId'],'instrument':{'sha256':binding['instrument']},'generator':{'tools':{'node':{'path':str(NODE)}}},
           'cadence':{'loadSeconds':0,'idleSeconds':1},'profileSelection':{'sha256':'5'*64},'tenants':2,'replicas':1,'hostIdentity':'6'*64}
        digest=hashlib.sha256(json.dumps(['evaluator-work-v2',config['checkpoint'],'evaluator-sample'],separators=(',',':')).encode()).hexdigest()
        def row(tenant,step):
            clock=str(10+step if tenant==A else 10);revision=1+step if tenant==A else 1
            return {'tenant':tenant,'stamp':clock,'reader':binding,'state':{'kind':config['kind'],'observed':{'clock':clock},'completed':{'clock':clock},
                    'output':{'tenant':tenant,'identity':'7'*64,'contentDigest':'8'*64,'outputRevision':revision,'restoreGeneration':None}},
                    'typed':{'version':2,'contractDigest':digest,'observed':[clock,None,None,None,None,None],'completed':[clock,None,None,None,None,None],
                             'identity':'7'*64,'digest':'8'*64,'revision':str(revision),'generation':None,'enabled':True,'arrayBounds':True,'bodyMetadataAbsent':True}}
        return d,out,m,row

    def exercise(self,*,stale=False,missing=False,health=False,initial=False,malformed=False):
        d,out,m,row=self.fixture();sql_calls=[];rpc_calls=[]
        def sql(directory,query,database,**kwargs):
            step=len(sql_calls);sql_calls.append((query,database,kwargs))
            self.assertEqual(directory,d);self.assertEqual(database,'synthetic_test');self.assertIn('SET LOCAL statement_timeout=',query)
            self.assertNotIn('jsonb_agg(e.doc)',query,'metadata collection must not read marker history')
            self.assertNotIn("THEN (c.projection->0->'output')",query,'metadata collection must not transport full clinical payload')
            rows=[row(A,step),row(B,step)]
            if initial:
                for r in rows:
                    r['state'].update(observed={'bootstrap':'0'},completed={},output=None)
                    r['typed'].update(observed=[None,None,None,None,None,'0'],completed=[None]*6,identity=None,digest=None,revision='0',generation=None)
            if malformed:
                rows[0]['typed']['contractDigest']='invalid-sensitive-sentinel'
                rows[0]['state']['output']['result']={'sensitive':'must-not-be-retained'}
            if stale and step==2:rows[0]['typed']['completed'][0]='11';rows[0]['state']['completed']['clock']='11'
            if missing and step==1:rows.pop(0)
            return '\n'.join(json.dumps(r) for r in rows)+'\n'
        def rpc(directory,service,*args):
            step=len(rpc_calls);rpc_calls.append(step);frame=fixtures.Progress().frame()
            frame['observedAt']=int(time.time()*1000)
            for r in frame['view']['tenants']:
                r.update(dueAt=None,dueReason=None,jobs=dict.fromkeys(('running','booting','acquire','time','parentAcquire','parentTime'),False))
                if r['tenant']==A:r['progress']['completedAcquisitions']+=step;r['cycles']+=step
                if health and step==1 and r['tenant']==B:r['progress']['failedCompletions']=1
            return json.dumps(frame)+'\n'
        caught=None;observer=None
        with mock.patch.object(a,'progress_services',return_value=['evaluator']),mock.patch.object(a,'psql',side_effect=sql),mock.patch.object(a,'progress_fetch',side_effect=rpc):
            try:
                observer=a.observe_progress(d,m,out,'load');observer.__enter__();observer.thread.join(timeout=5);observer.__exit__(None,None,None)
            except Exception as error:caught=error
        return d,out,m,observer,caught,sql_calls,rpc_calls

    def test_actual_caller_invokes_three_sql_reader_and_rpc_rounds_and_persists_verifiable_capture_and_cost(self):
        d,out,m,observer,error,sql,rpc=self.exercise();self.assertIsNone(error)
        self.assertEqual(len(sql),3);self.assertEqual(len(rpc),3)
        proof=a.document(out/'evaluator-progress.json');self.assertEqual(proof['kind'],'evaluator-opportunity-phase-v1')
        self.assertEqual(len(proof['durable']),3);self.assertEqual(len(proof['captureWindows']),3)
        self.assertEqual(o.verify(proof,2,['evaluator'],BINDING,source_sha256=a.digest(d/'completion-source.json'))['verdict'],'PASS')
        self.assertEqual(proof['eligibleTenants'],1);self.assertEqual(proof['byTenant'][B]['classification'],'NO_KNOWN_OPPORTUNITY')
        self.assertIsNone(proof['workWindowSeconds']);self.assertTrue(proof['workRate'].startswith('UNMEASURED'))
        costs=proof['durableCollectorCost'];self.assertEqual(costs['preparation']['nodeCalls'],1)
        self.assertEqual(sum(c['sqlQueries'] for c in costs['rounds']),3)
        self.assertTrue(all(c['rawSqlBytes']>0 and c['wallSeconds']>=0 for c in costs['rounds']))
        summary=a.progress_summary(out);self.assertNotIn('durable',summary);self.assertNotIn('byTenant',summary)
        bad=copy.deepcopy(proof);bad['durable'].pop()
        with self.assertRaisesRegex(p.Refused,'CAPTURE'):o.verify(bad,2,['evaluator'],BINDING)
        bad=copy.deepcopy(proof);bad['durableCollectorCost']['rounds']=[]
        with self.assertRaisesRegex(p.Refused,'COST'):o.verify(bad,2,['evaluator'],BINDING)
        bad=copy.deepcopy(proof);bad['captureWindows'][1]['startNs']=0
        with self.assertRaisesRegex(p.Refused,'ORDER'):o.verify(bad,2,['evaluator'],BINDING)
        with self.assertRaisesRegex(p.Refused,'BINDING'):o.verify(proof,2,['evaluator'],BINDING,source_sha256='0'*64)
        self.assertEqual(o.verify(proof,2,['evaluator'],BINDING)['verdict'],'PASS')

    def test_actual_initial_reader_collects_three_rounds_but_remains_unmeasured_pending(self):
        _,out,_,_,error,sql,rpc=self.exercise(initial=True)
        self.assertEqual(str(error),'M7_OPPORTUNITY_NOT_OBSERVED')
        self.assertEqual(len(sql),3);self.assertEqual(len(rpc),3)
        proof=a.document(out/'evaluator-progress.json')
        self.assertEqual(proof['verdict'],'UNMEASURED')
        self.assertEqual(proof['classifications']['KNOWN_PENDING'],2)
        self.assertEqual(proof['durable'][0]['rows'][0]['completed'],{})

    def test_actual_typed_failure_retains_only_bounded_predicates_in_existing_receipt(self):
        _,out,_,_,error,_,_=self.exercise(malformed=True)
        self.assertEqual(str(error),'M7_COMPLETION_TYPED_STATE');self.assertEqual(error.verdict,'FAIL')
        proof=a.document(out/'evaluator-progress.json')
        diagnostic=proof['failedCollection']['completionReader']
        self.assertEqual(set(diagnostic),{'rowIndex','predicates'})
        self.assertEqual(diagnostic['rowIndex'],0)
        self.assertFalse(diagnostic['predicates']['contractDigestMatches'])
        self.assertTrue(all(type(v) is bool for v in diagnostic['predicates'].values()))
        raw=json.dumps(proof)
        for secret in ('invalid-sensitive-sentinel','must-not-be-retained','sensitive'):
            self.assertNotIn(secret,raw)
        self.assertLess(len(json.dumps(diagnostic)),1024)
        self.assertEqual(proof['durableCollectorCost']['rounds'][0]['nodeCalls'],1,'FAILED_NODE_INVOCATION_IS_WORK')

    def test_removing_actual_node_failure_projection_is_red_then_restored(self):
        def criterion():
            _,out,_,_,_,_,_=self.exercise(malformed=True)
            self.assertIn('completionReader',a.document(out/'evaluator-progress.json')['failedCollection'])
        criterion();real=a.command
        def drop_projection(*args,**kwargs):
            raw=real(*args,**kwargs);value=json.loads(raw)
            if isinstance(value,dict):value.pop('completionDiagnostic',None)
            return json.dumps(value)
        with mock.patch.object(a,'command',side_effect=drop_projection):
            with self.assertRaises(TypeError):criterion()
        criterion()

    def test_removing_actual_observer_sql_capture_is_red_then_restored(self):
        def criterion():
            _,_,_,_,error,sql,_=self.exercise();self.assertIsNone(error);self.assertEqual(len(sql),3)
        criterion()
        def inspection_only(observer):observer.rounds.append(idle.round_view(observer.services,observer.ids,observer.fetch))
        with mock.patch.object(o.Observer,'observe',inspection_only):
            with self.assertRaises(AssertionError):criterion()
        criterion()

    def test_actual_stale_or_missing_capture_refuses_and_preserves_partial_evidence(self):
        for kwargs,code in [({'stale':True},'NOT_OBSERVED'),({'missing':True},'COVERAGE')]:
            _,out,_,_,error,sql,_=self.exercise(**kwargs)
            self.assertIsNotNone(error);self.assertIn(code,str(error));self.assertEqual(error.verdict,'UNMEASURED')
            proof=a.document(out/'evaluator-progress.json');self.assertEqual(proof['verdict'],'UNMEASURED')
            self.assertGreaterEqual(len(proof['durableCollectorCost']['rounds']),2)
            if kwargs.get('stale'):self.assertEqual(proof['byTenant'][A]['classification'],'KNOWN_PENDING')

    def test_actual_all_roster_hidden_failure_remains_fail_for_untouched_tenant(self):
        _,out,_,_,error,_,_=self.exercise(health=True)
        self.assertIsNotNone(error);self.assertEqual(error.verdict,'FAIL');self.assertIn('HIDDEN_FAILURE',str(error))
        self.assertEqual(a.document(out/'evaluator-progress.json')['verdict'],'FAIL')

    def test_default_is_legacy_and_unsupported_or_missing_source_refuses_before_sql(self):
        d,out,m,_=self.fixture()
        with mock.patch.object(a,'progress_services',return_value=['evaluator']),mock.patch.object(a,'psql',side_effect=AssertionError('NO_SQL')):
            legacy={**m};legacy.pop('evaluatorOpportunities')
            self.assertIs(type(a.observe_progress(d,legacy,out,'load')),p.Observer)
            bad={**m,'completionContract':'evaluator-work-v1'}
            with self.assertRaisesRegex(RuntimeError,'PROFILE_UNSUPPORTED'):a.observe_progress(d,bad,out,'load')
            with self.assertRaisesRegex(RuntimeError,'PROFILE_UNSUPPORTED'):a.observe_progress(d,{**m,'evaluatorOpportunities':''},out,'load')
            config=a.document(d/'completion-source.json');config['selection']={};a.write(d/'completion-source.json',config)
            with self.assertRaisesRegex(RuntimeError,'SELECTED_PROFILE_UNSUPPORTED'):a.observe_progress(d,m,out,'load')
            (d/'completion-source.json').unlink()
            with self.assertRaisesRegex(RuntimeError,'SOURCE_REQUIRED'):a.observe_progress(d,m,out,'load')

    def test_explicit_prepare_selection_is_not_a_default_or_profile_fallback(self):
        import argparse
        m={'profile':'pgstream-sample','completionContract':'evaluator-work-v2','runPurpose':'discovery'}
        a.select_opportunities(argparse.Namespace(),m);self.assertNotIn('evaluatorOpportunities',m)
        a.select_opportunities(argparse.Namespace(evaluator_opportunities=o.CONTRACT),m);self.assertEqual(m['evaluatorOpportunities'],o.CONTRACT)
        with self.assertRaisesRegex(RuntimeError,'PROFILE_UNSUPPORTED'):a.select_opportunities(argparse.Namespace(evaluator_opportunities=o.CONTRACT),{'profile':'capacity'})

    def test_actual_capture_byte_and_deadline_bounds_refuse_before_decoding_or_querying(self):
        d,_,m,_=self.fixture();collector=a.opportunity_collector(d,m,[A,B])
        with mock.patch.object(a,'psql',return_value='x'*100) as sql,mock.patch.object(o,'ROUND_BYTES',10):
            with self.assertRaisesRegex(p.Refused,'BYTE_BOUND') as caught:collector()
            self.assertEqual(caught.exception.opportunityCost['rawSqlBytes'],100);self.assertEqual(sql.call_count,1)
        with mock.patch.object(a,'psql',side_effect=AssertionError('NO_QUERY_AFTER_DEADLINE')) as sql,mock.patch.object(o,'ROUND_SECONDS',0):
            with self.assertRaisesRegex(p.Refused,'DEADLINE'):collector()
            sql.assert_not_called()


if __name__=='__main__':unittest.main()
