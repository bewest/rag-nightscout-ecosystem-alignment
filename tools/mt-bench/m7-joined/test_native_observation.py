"""Verify native snapshots survive the actual durable opportunity reducer."""
import copy,inspect,json,subprocess,unittest
from pathlib import Path
import evaluator_opportunities as o
import evaluator_progress as p
HERE=Path(__file__).resolve().parent
class NativeObservation(unittest.TestCase):
 def fixture(self):
  script="const d=process.argv[1],f=require(d+'/native-observation-fixture.cjs'),o=require(d+'/completed-oracle.cjs');console.log(JSON.stringify({binding:f.config.binding,capture:o.progressSnapshot([f.row],f.config,[f.row.tenant])}));"
  v=json.loads(subprocess.check_output(['node','-e',script,str(HERE)],text=True,timeout=5));return v['binding'],[copy.deepcopy(v['capture']) for _ in range(3)]
 def test_actual_native_reader_and_opportunity_reducer_keep_distinct_positions(self):
  b,c=self.fixture();tenant=c[0]['rows'][0]['tenant'];rows=o.durable_rows(c,[tenant],b)
  self.assertEqual(rows[0][tenant]['writerClock'],'9007199254740993');self.assertEqual(rows[0][tenant]['native']['inputFloor'],'2')
  self.assertEqual(rows[0][tenant]['native']['acceptedPosition'],'0/200');self.assertEqual(rows[0][tenant]['outputRevision'],'1')
 def test_missing_corrupt_native_and_reset_refuse_then_restore(self):
  b,c=self.fixture();tenant=c[0]['rows'][0]['tenant']
  for change,code in [(lambda r:r.pop('native'),'NATIVE'),(lambda r:r['native'].update(acceptedPosition='invalid'),'NATIVE_POSITION'),(lambda r:r['native']['raw'].update(kind='bad'),'NATIVE_RAW'),(lambda r:r['observed'].update(bootstrap='3'),'NATIVE')]:
   bad=copy.deepcopy(c)
   for cap in bad:change(cap['rows'][0])
   with self.assertRaisesRegex(p.Refused,code):o.durable_rows(bad,[tenant],b)
   o.durable_rows(c,[tenant],b)
  for change in [lambda r:r['native']['source'].update(system_id='2'),lambda r:r['native'].update(inputFloor='1',completedInputFloor='1'),lambda r:r['native'].update(acceptedPosition='0/100')]:
   bad=copy.deepcopy(c);change(bad[1]['rows'][0])
   with self.assertRaises(p.Refused):o.durable_rows(bad,[tenant],b)
   o.durable_rows(c,[tenant],b)
 def test_invalidation_snapshot_sentinel_is_not_acceptance_regression(self):
  b,c=self.fixture();tenant=c[0]['rows'][0]['tenant']
  c[1]['rows'][0]['native']['snapshotPosition']='0/0'
  self.assertEqual(len(o.durable_rows(c,[tenant],b)),3)

 def test_actual_native_validator_ablation_loses_corrupt_raw_refusal(self):
  b,c=self.fixture();tenant=c[0]['rows'][0]['tenant'];bad=copy.deepcopy(c)
  for cap in bad:cap['rows'][0]['native']['raw']['kind']='bad'
  source=inspect.getsource(o.durable_rows);needle="native_row(row.get('native'))";self.assertEqual(source.count(needle),1)
  ns=dict(o.__dict__);exec(compile(source.replace(needle,'None'),o.__file__,'exec'),ns)
  def criterion(fn):
   with self.assertRaisesRegex(p.Refused,'NATIVE_RAW'):fn(bad,[tenant],b)
  criterion(o.durable_rows)
  with self.assertRaises(AssertionError):criterion(ns['durable_rows'])
  criterion(o.durable_rows);o.durable_rows(c,[tenant],b)
if __name__=='__main__':unittest.main()
