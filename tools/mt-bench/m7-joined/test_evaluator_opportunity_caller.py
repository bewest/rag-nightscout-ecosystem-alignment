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

    def exercise(self,*,health=False):
        d,out,m,row=self.fixture();sql_calls=[];rpc_calls=[]
        def sql(*args,**kwargs):
            sql_calls.append(args)
            self.fail('ordinary progress invoked the retired opportunity reader')
        def rpc(directory,service,*args,**options):
            step=len(rpc_calls);rpc_calls.append(step);frame=fixtures.Progress().frame()
            frame['observedAt']=int(time.time()*1000)
            for r in frame['view']['tenants']:
                r.update(dueAt=None,dueReason=None,jobs=dict.fromkeys(('running','booting','acquire','time','parentAcquire','parentTime'),False))
                if r['tenant']==A:r['progress']['completedAcquisitions']+=step;r['cycles']+=step
                # Rejected attempts are not individually classified clinical
                # failures. Explicit clinical errors and counter resets remain
                # separate refusing observations on the untouched tenant.
                if r['tenant']==B:
                    if health is True and step==1:r['evaluation']['alert']='SYNTHETIC_CLINICAL_FAILURE'
                    if health=='counter' and step>=1:r['progress']['failedCompletions']=1
                    if health=='reset' and step==1:r['progress']['failedCompletions']=1
            return json.dumps(frame)+'\n'
        caught=None;observer=None
        with mock.patch.object(a,'progress_services',return_value=['evaluator']),mock.patch.object(a,'psql',side_effect=sql),mock.patch.object(a,'progress_fetch',side_effect=rpc):
            try:
                observer=a.observe_progress(d,m,out,'load');observer.__enter__();observer.thread.join(timeout=5);observer.__exit__(None,None,None)
            except Exception as error:caught=error
        return d,out,m,observer,caught,sql_calls,rpc_calls

    def test_ordinary_progress_does_not_read_opportunity_sql(self):
        _,out,_,_,error,sql_calls,rpc_calls=self.exercise()
        self.assertIsNone(error)
        self.assertEqual(sql_calls,[])
        self.assertEqual(len(rpc_calls),3)
        self.assertTrue(a.document(out/'evaluator-progress.json')['demandDriven'])

    def test_actual_all_roster_clinical_error_remains_fail_for_untouched_tenant(self):
        _,out,_,_,error,_,_=self.exercise(health=True)
        self.assertIsNotNone(error);self.assertEqual(error.verdict,'FAIL');self.assertEqual(str(error),'M7_EVALUATOR_PROGRESS_ERROR')
        proof=a.document(out/'evaluator-progress.json')
        self.assertEqual(proof['verdict'],'FAIL')
        self.assertEqual(proof['failedCollection']['diagnostic']['failedRow']['alert'],'SYNTHETIC_CLINICAL_FAILURE')
        self.assertIsNone(self.exercise()[4],'restored actual observer remains healthy')

    def test_actual_capture_byte_and_deadline_bounds_refuse_before_decoding_or_querying(self):
        d,_,m,_=self.fixture();collector=a.opportunity_collector(d,m,[A,B])
        with mock.patch.object(a,'psql',return_value='x'*100) as sql,mock.patch.object(o,'ROUND_BYTES',10):
            with self.assertRaisesRegex(p.Refused,'BYTE_BOUND') as caught:collector()
            self.assertEqual(caught.exception.opportunityCost['rawSqlBytes'],100);self.assertEqual(sql.call_count,1)
        with mock.patch.object(a,'psql',side_effect=AssertionError('NO_QUERY_AFTER_DEADLINE')) as sql,mock.patch.object(o,'ROUND_SECONDS',0):
            with self.assertRaisesRegex(p.Refused,'DEADLINE'):collector()
            sql.assert_not_called()


if __name__=='__main__':unittest.main()
