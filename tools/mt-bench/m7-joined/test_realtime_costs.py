import copy,json,tempfile,unittest
from pathlib import Path
import realtime_costs as c
UUID='11111111-1111-4111-8111-111111111111'
def view(n=1):return {'kind':'realtime','processIncarnation':UUID,'phase':'booted','ownerAvailable':True,'stats':{'version':1,'available':True,'runtime':{k:n for k in c.COUNTERS},'detector':{'available':True,'polls':n,'failures':0},'watchedCount':2}}
def book(n,start):
 r=c.parse(view(n));r['request']={'monotonicStartedAtNs':start,'monotonicFinishedAtNs':start+1}
 return {'version':1,'status':'MEASURED','owner':'a'*32,'hostIdentity':'b'*64,'pair':{'core':'c'*40,'deploy':'d'*40},'imageId':'sha256:'+'e'*64,'services':{'realtime':r}}
class Realtime(unittest.TestCase):
 def test_exact_counters_and_bookend_gauge(self):
  r=c.assess(book(1,1),book(5,11))['services']['realtime'];self.assertEqual(r['runtimeDelta']['detected'],4);self.assertEqual(r['detectorDelta']['polls'],4);self.assertEqual(r['watchedCount']['before'],2)
 def test_unsupported_unavailable_and_no_fallback(self):
  v=view();v.pop('stats');self.assertEqual(c.parse(v)['status'],'NO-INSTRUMENT')
  v=view();v['stats'].update(available=False,runtime=None,watchedCount=None);v['stats']['detector']={'available':False,'polls':None,'failures':None};self.assertEqual(c.parse(v)['status'],'NO-INSTRUMENT')
  v['stats']['watchedCount']=0
  with self.assertRaisesRegex(RuntimeError,'UNAVAILABLE_NOT_ZERO'):c.parse(v)
  a,b=book(1,1),book(5,11)
  for x in (a,b):x['services']['realtime']['stats']['detector']={'available':False,'polls':None,'failures':None}
  self.assertEqual(c.assess(a,b)['services']['realtime']['detectorDelta'],{'status':'NO-INSTRUMENT'})
 def test_process_source_reset_capability_and_timing_controls(self):
  changes=[(lambda b:b['services']['realtime'].update(processIncarnation='22222222-2222-4222-8222-222222222222'),'PROCESS_CHANGED'),(lambda b:b.update(owner='f'*32),'SOURCE_OWNER_CHANGED'),(lambda b:b['services']['realtime']['stats']['runtime'].update(refreshes=0),'RESET'),(lambda b:b['services']['realtime']['stats']['detector'].update(polls=0),'RESET'),(lambda b:b['services']['realtime']['request'].update(monotonicStartedAtNs=1),'TIMING'),(lambda b:b.update(services={}),'ROSTER_CHANGED')]
  for change,error in changes:
   a,b=book(1,1),book(5,11);self.assertEqual(c.assess(a,b)['status'],'MEASURED');change(b)
   with self.subTest(error=error),self.assertRaisesRegex(RuntimeError,error):c.assess(a,b)
   self.assertEqual(c.assess(a,book(5,11))['status'],'MEASURED')
 def test_malformed_boolean_and_watch_bound_refuse(self):
  # watchedCount is a source gauge, not the reference population ceiling.
  v=view();v['stats']['watchedCount']=12001;self.assertEqual(c.parse(v)['stats']['watchedCount'],12001)
  for change in (lambda v:v['stats']['runtime'].update(ticks=True),lambda v:v['stats'].update(watchedCount=2**53),lambda v:v['stats'].update(version=4),lambda v:v['stats'].update(version=True)):
   v=view();change(v)
   with self.assertRaises(RuntimeError):c.parse(v)
 def test_optional_delivery_exact_deltas_and_unavailable_not_zero(self):
  a,b=book(1,1),book(5,11)
  self.assertEqual(c.assess(a,b)['services']['realtime']['deliveryDelta']['status'],'NO-INSTRUMENT')
  a['services']['realtime']['stats']['delivery']=None
  b['services']['realtime']['stats']['delivery']={**{k:10 for k in c.DELIVERY_COUNTERS},'maxMetadataBatch':16}
  self.assertEqual(c.assess(a,b)['services']['realtime']['deliveryDelta']['status'],'NO-INSTRUMENT')
  a['services']['realtime']['stats']['delivery']={**{k:2 for k in c.DELIVERY_COUNTERS},'maxMetadataBatch':4}
  r=c.assess(a,b)['services']['realtime']['deliveryDelta'];self.assertEqual(r['counterDelta']['metadataRows'],8);self.assertEqual(r['maxMetadataBatch']['after'],16);self.assertNotIn('maxMetadataBatch',r['counterDelta'])
  b['services']['realtime']['stats']['delivery']['metadataRows']=1
  with self.assertRaisesRegex(RuntimeError,'RESET'):c.assess(a,b)
  b['services']['realtime']['stats']['delivery']['metadataRows']=10
  self.assertEqual(c.assess(a,b)['services']['realtime']['deliveryDelta']['status'],'MEASURED')
 def test_delivery_shape_bounds_and_reset_controls(self):
  for change in (lambda d:d.pop('metadataRows'),lambda d:d.update(metadataRows=True),lambda d:d.update(metadataRows=-1),lambda d:d.update(extra=0),lambda d:d.update(maxMetadataBatch=65)):
   v=view();v['stats']['delivery']={**{k:1 for k in c.DELIVERY_COUNTERS},'maxMetadataBatch':1};self.assertEqual(c.parse(v)['status'],'MEASURED');change(v['stats']['delivery'])
   with self.assertRaisesRegex(RuntimeError,'DELIVERY'):c.parse(v)
  a,b=book(1,1),book(5,11)
  for x in (a,b):x['services']['realtime']['stats']['delivery']={**{k:1 for k in c.DELIVERY_COUNTERS},'maxMetadataBatch':4}
  b['services']['realtime']['stats']['delivery']['maxMetadataBatch']=3
  with self.assertRaisesRegex(RuntimeError,'RESET'):c.assess(a,b)
 def test_one_read_each_no_source_failure_detail_published(self):
  with tempfile.TemporaryDirectory()as d:
   calls=[]
   def fetch(service):calls.append(service);return json.dumps(view())
   owner={k:v for k,v in book(1,1).items() if k in ('owner','hostIdentity','pair','imageId')}
   r=c.capture(Path(d),'before',owner,['realtime'],fetch);self.assertEqual(calls,['realtime']);self.assertEqual(r['status'],'MEASURED')
   def fail(service):raise RuntimeError('PRIVATE CREDENTIAL')
   r=c.capture(Path(d),'after',owner,['realtime'],fail);self.assertEqual(r['status'],'NO-INSTRUMENT');self.assertNotIn('PRIVATE',json.dumps(r))
if __name__=='__main__':unittest.main()
