import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cost_companion as c

def snapshot(calls=1,rows=2,wal=3):
 return {'version':1,'statsReset':'synthetic-reset','dealloc':0,'statements':[{'role':'synthetic-shared','queryid':'1','dbid':'2','queryHex':'SELECT 1'.encode().hex(),'calls':calls,'rows':rows,'walBytes':wal,'walAvailable':True,'toplevel':True}], 'databases':[{'dbid':'2','name':'synthetic','commits':calls,'rollbacks':0,'statsReset':None}]}
def book(value,start):
 return {'status':'MEASURED','collectorOwner':'a'*32,'hostIdentity':'b'*64,'pair':{'core':'c'*40,'deploy':'d'*40},'imageId':'sha256:'+'e'*64,'request':{'monotonicStartedAtNs':start,'monotonicFinishedAtNs':start+1},'snapshot':value}

class Costs(unittest.TestCase):
 def test_statement_rows_wal_and_shared_database_deltas(self):
  a,b=book(snapshot(),1),book(snapshot(5,9,12),11);r=c.assess(a,b)
  self.assertEqual(r['byRole']['synthetic-shared'],{'calls':4,'rows':7,'walBytes':9,'walStatus':'MEASURED'})
  self.assertEqual(r['databaseTransactions'][0]['commits'],4)
  self.assertIn('collector',r['transactionScope']);self.assertEqual(r['wireRoundTrips'],'NO-INSTRUMENT')
 def test_missing_wal_capability_is_not_zero_and_capability_change_refuses(self):
  a,b=book(snapshot(),1),book(snapshot(5,9,12),11)
  for v in (a,b):v['snapshot']['statements'][0].update(walAvailable=False,walBytes=None)
  self.assertIsNone(c.assess(a,b)['byRole']['synthetic-shared']['walBytes'])
  self.assertEqual(c.assess(a,b)['byRole']['synthetic-shared']['walStatus'],'NO-INSTRUMENT')
  b['snapshot']['statements'][0].update(walAvailable=True,walBytes=0)
  with self.assertRaisesRegex(RuntimeError,'CAPABILITY_CHANGED'):c.assess(a,b)
 def test_reset_eviction_identity_timing_and_negative_delta_refuse(self):
  changes=[(lambda x:x['snapshot'].update(statsReset='changed'),'RESET_OR_EVICTION'),(lambda x:x['snapshot'].update(dealloc=1),'RESET_OR_EVICTION'),(lambda x:x['snapshot'].update(statements=[]),'STATEMENT_EVICTED'),(lambda x:x.update(collectorOwner='f'*32),'OWNER_SOURCE_CHANGED'),(lambda x:x.update(imageId='sha256:'+'f'*64),'OWNER_SOURCE_CHANGED'),(lambda x:x['request'].update(monotonicStartedAtNs=1),'TIMING'),(lambda x:x['snapshot']['statements'][0].update(rows=0),'COUNTER_RESET'),(lambda x:x['snapshot']['databases'][0].update(commits=0),'DATABASE_RESET'),(lambda x:x['snapshot']['databases'][0].update(statsReset='changed'),'DATABASE_RESET')]
  for change,error in changes:
   a,b=book(snapshot(),1),book(snapshot(5,9,12),11);self.assertEqual(c.assess(a,b)['status'],'MEASURED');change(b)
   with self.subTest(error=error),self.assertRaisesRegex(RuntimeError,error):c.assess(a,b)
   self.assertEqual(c.assess(a,book(snapshot(5,9,12),11))['status'],'MEASURED')
 def test_shape_missing_fields_and_duplicate_do_not_become_green(self):
  for field in ('rows','calls','walAvailable','queryHex'):
   v=snapshot();del v['statements'][0][field]
   with self.subTest(field=field),self.assertRaises(RuntimeError):c.validate(v)
  v=snapshot();v['version']=True
  with self.assertRaisesRegex(RuntimeError,'VERSION'):c.validate(v)
  v=snapshot();v['statements']*=2
  with self.assertRaisesRegex(RuntimeError,'DUPLICATE_STATEMENT'):c.validate(v)
 def test_adapter_captures_companions_without_changing_original_statement_query(self):
  import adapter as a
  from test_realtime_costs import view
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);a.write(p/'owner.json',{'owner':'a'*32,'hostIdentity':'b'*64,'pair':{'core':'c'*40,'deploy':'d'*40},'imageId':'sha256:'+'e'*64})
   a.write(p/'frozen.compose.json',{'services':{'realtime':{'command':['node','serve','realtime']}}});queries=[]
   def sql(_,text):
    queries.append(text);return json.dumps(snapshot()) if text==c.SQL else 'unchanged-six-column-row'
   with patch.object(a,'resources',return_value=[]),patch.object(a,'psql',side_effect=sql),patch.object(a,'compose',return_value=json.dumps(view())) as rpc:
    a.phase_snapshot(p,p,'before')
   self.assertEqual((p/'before-pg-statements.tsv').read_text(),'unchanged-six-column-row')
   self.assertEqual(json.loads((p/'before-pg-costs.json').read_text())['status'],'MEASURED')
   self.assertEqual(json.loads((p/'before-realtime-costs.json').read_text())['status'],'MEASURED')
   self.assertEqual(rpc.call_count,1);self.assertEqual(rpc.call_args.args[1:5],('exec','-T','realtime','node'));self.assertEqual(rpc.call_args.kwargs['timeout'],7)
   self.assertEqual(len(queries),3)
 def test_capture_failure_is_explicit_no_instrument_not_fabricated_zero(self):
  with tempfile.TemporaryDirectory()as d:
   owner={'owner':'a'*32,'hostIdentity':'b'*64,'pair':{},'imageId':'synthetic'}
   p=Path(d);r=c.capture(p,'before',owner,lambda q:json.dumps(snapshot()))
   self.assertEqual(r['status'],'MEASURED');self.assertTrue((p/'before-pg-costs.json').is_file())
   def fail(q):raise RuntimeError('PRIVATE SQL DETAIL')
   r=c.capture(p,'after',owner,fail);self.assertEqual(r['status'],'NO-INSTRUMENT');self.assertNotIn('PRIVATE',json.dumps(r));self.assertNotIn('snapshot',r)
   self.assertEqual(c.assess(json.loads((p/'before-pg-costs.json').read_text()),r)['status'],'NO-INSTRUMENT')
if __name__=='__main__':unittest.main()
