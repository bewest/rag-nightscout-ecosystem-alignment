"""Actual v2 oracle against synthetic rows and mocked SUT SQL only."""
import copy,hashlib,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'m7-joined'))
import adapter as a,component_sut as sut,protocol
sys.path.insert(0,str(Path(__file__).resolve().parent))

def fixture():
 source=(a.HERE/'completed-oracle-v2-control.cjs').read_text().split('const assess=value=>')[0];value=json.loads(subprocess.check_output(['node','-e',source+'console.log(JSON.stringify({row,witness,config}));'],cwd=a.HERE,text=True));return value

def files(root,viewers):
 f=fixture();rows=[];witnesses=[];tenants=[]
 for i in range(16):
  tenant=f'{i+1:08x}-1111-4111-8111-111111111111';tenants.append({'id':tenant});row=copy.deepcopy(f['row']);row['tenant']=tenant;row['state']['output']['tenant']=tenant;docs=[{'_id':f'synthetic-{i}-{j}','date':123456789+i*100+j,'sgv':123}for j in range(2)];sgvs=[{'_id':x['_id'],'mills':x['date'],'mgdl':x['sgv']}for x in docs];row['stored']=docs;output=row['state']['output'];output['rows']=[{'domain':'entries','doc':x}for x in docs];output['frame']={'sgvs':sgvs};output['result']['properties']['bgnow']={'mean':123,'last':123,'mills':docs[-1]['date'],'sgvs':sgvs};rows.append(row)
  for j,doc in enumerate(docs):witnesses.append({'tenant':tenant,'date':doc['date'],'acked':True,'clients':[{'socket':k,'connects':1,'sgv':sgvs[j]}for k in range(viewers)]})
 (root/'load').mkdir();protocol.write(root/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':'component_application_test'}}}});protocol.write(root/'tenants.private.json',tenants);protocol.write(root/'completion-source.json',f['config']);protocol.write(root/'load/probe.json',{'clientWitnesses':witnesses,'window':{'writes':{'ok':32,'failed':0}}});protocol.write(root/'load/fanout.json',{'probeWrites':{'byTenant':{x['id']:2 for x in tenants}}});(root/'load/runid').write_text('synthetic-component');return f,rows,witnesses,tenants
class Sut(unittest.TestCase):
 def test_actual_v2_selected_case_one_four_clients_and_refusal_restoration(self):
  for viewers in(1,4):
   with tempfile.TemporaryDirectory()as folder:
    d=Path(folder);f,rows,witnesses,tenants=files(d,viewers);case={'id':'evrt-case','kind':'evrt','rate':0,'seconds':32,'sampleTenants':16,'viewers':viewers,'probeEveryMs':1000,'maxWrites':32};m={'pair':f['config']['binding']['pair'],'imageId':f['config']['binding']['imageId'],'tenants':16};calls=[]
    def sql(directory,query,database='postgres'):
     calls.append(database)
     if database!='component_application_test':raise RuntimeError('42P01 mocked application relation absent')
     return'\n'.join(map(json.dumps,rows))
    with patch.object(a,'psql',side_effect=sql):
     self.assertEqual(sut.completed(d,m,case,maximum=0)['verdict'],'PASS');self.assertEqual(calls[-1],'component_application_test')
     bad=copy.deepcopy(witnesses);bad[0]['clients']=bad[0]['clients'][:-1];protocol.write(d/'load/probe.json',{'clientWitnesses':bad});self.assertEqual(sut.completed(d,m,case,maximum=0)['verdict'],'UNMEASURED')
     protocol.write(d/'load/probe.json',{'clientWitnesses':witnesses});rows[0]['state']['output']['result']['properties']['bgnow']['mean']=124
     with self.assertRaisesRegex(RuntimeError,'SEMANTIC_OUTPUT_REFUSAL'):sut.completed(d,m,case,maximum=0)
     rows[0]['state']['output']['result']['properties']['bgnow']['mean']=123;self.assertEqual(sut.completed(d,m,case,maximum=0)['verdict'],'PASS')
     with patch.object(a,'application_database',return_value='postgres'):
      with self.assertRaisesRegex(RuntimeError,'42P01'):sut.completed(d,m,case,maximum=0)
     self.assertEqual(sut.completed(d,m,case,maximum=0)['verdict'],'PASS')
 def test_probe_uncertainty_preserved_without_fake_k6_file(self):
  with tempfile.TemporaryDirectory()as folder:
   d=Path(folder);f,rows,witnesses,tenants=files(d,1);case={'kind':'evrt'};witnesses[0]['acked']=False;protocol.write(d/'load/probe.json',{'clientWitnesses':witnesses});probes={x['id']:2 for x in tenants};probes[tenants[0]['id']]=1;protocol.write(d/'load/fanout.json',{'probeWrites':{'byTenant':probes}});stored={x['id']:{'probe':2}for x in tenants}
   with patch.object(a,'stored',return_value=stored):result=sut.counts(d,{'tenants':16},case)
   self.assertFalse(result['probeExact']);self.assertEqual(sum(x['uncertainUpperBound']for x in result['probeConservativeBounds']),1);self.assertFalse((d/'load/k6-summary.json').exists())
if __name__=='__main__':unittest.main()
