"""Offline actual-clinical explicit database regression; no PostgreSQL/network."""
import copy,importlib.util,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'m7-joined'))
import clinical,protocol
sys.path.insert(0,str(Path(__file__).resolve().parent))

class Database(unittest.TestCase):
 def test_actual_frozen_database_and_missing_argument_ablation(self):
  tenant='11111111-1111-4111-8111-111111111111';stamp='9007199254740993';doc={'_id':'synthetic-id','date':123456789,'sgv':123};sgv={'_id':doc['_id'],'mills':doc['date'],'mgdl':123};chosen={'kind':'evaluator-work-v1','pair':{'core':'1'*40,'deploy':'2'*40},'imageId':'sha256:'+'3'*64,'instrument':'4'*64}
  row={'tenant':tenant,'stamp':stamp,'reader':chosen,'stored':[doc],'state':{'kind':'evaluator-work-v1','observed':{'clock':stamp},'completed':{'clock':stamp},'output':{'tenant':tenant,'inputCheckpoint':stamp,'outputRevision':3,'contentDigest':'a'*64,'result':{'properties':{'bgnow':{'mean':123,'last':123,'mills':doc['date'],'sgvs':[sgv]}}},'rows':[{'domain':'entries','doc':doc}],'frame':{'sgvs':[sgv]}}}}
  witness={'tenant':tenant,'date':doc['date'],'acked':True,'clients':[{'socket':i,'connects':1,'sgv':sgv}for i in range(2)]}
  with tempfile.TemporaryDirectory()as folder:
   d=Path(folder);(d/'load').mkdir();protocol.write(d/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':'frozen_application_test'}}}});protocol.write(d/'completion-source.json',{'clock':'sample_clock','checkpoint':'sample_checkpoint','entries':'sample_entries','consumer':'evaluator-sample-completed','kind':'evaluator-work-v1','binding':chosen});protocol.write(d/'tenants.private.json',[{'id':tenant}]);protocol.write(d/'load/probe.json',{'clientWitnesses':[witness]});(d/'load/runid').write_text('synthetic-run')
   calls=[]
   def psql(directory,query,database='postgres'):
    calls.append(database)
    if database!='frozen_application_test':raise RuntimeError('42P01: application relation absent from postgres')
    return json.dumps(row)
   with patch.object(clinical.a,'psql',side_effect=psql):
    self.assertEqual(clinical.completed(d,{'tenants':1},maximum=0)['verdict'],'PASS');self.assertEqual(calls,['frozen_application_test'])
    source=Path(clinical.__file__).read_text();before='a.psql(d,query,a.application_database(d))';self.assertEqual(source.count(before),1);broken=types.ModuleType('ablate_explicit_database');exec(compile(source.replace(before,'a.psql(d,query)'),'<missing-explicit-database-control>','exec'),broken.__dict__)
    with self.assertRaisesRegex(RuntimeError,'42P01'):broken.completed(d,{'tenants':1},maximum=0)
    self.assertEqual(calls[-1],'postgres');self.assertEqual(clinical.completed(d,{'tenants':1},maximum=0)['verdict'],'PASS');self.assertEqual(calls[-1],'frozen_application_test')
if __name__=='__main__':unittest.main()
