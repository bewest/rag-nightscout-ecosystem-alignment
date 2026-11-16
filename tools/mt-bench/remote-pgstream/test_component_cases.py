"""Focused pure-case and actual existing command-builder controls; no actors."""
import copy,importlib.util,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import component_cases as c,protocol,generator,cell
_s=importlib.util.spec_from_file_location('remote_component_fixtures',Path(__file__).with_name('test_contract.py'));_m=importlib.util.module_from_spec(_s);_s.loader.exec_module(_m);selected=_m.selected
import sys;sys.path.insert(0,str(Path(__file__).resolve().parent))

def cases():return{'version':1,'cases':[{'id':'rest-180','kind':'rest','rate':180,'seconds':310,'sampleTenants':16,'viewers':2,'probeEveryMs':300000,'maxWrites':2},*({'id':'evrt-v'+str(v),'kind':'evrt','rate':0,'seconds':32,'sampleTenants':16,'viewers':v,'probeEveryMs':1000,'maxWrites':32}for v in(1,2,4))]}
class Components(unittest.TestCase):
 def test_actual_protocol_optional_case_binding_and_negative_controls(self):
  b=selected();b['componentCases']=cases();self.assertIs(protocol.binding(b,1000),b)
  for mutate in(lambda x:x['cases'][1].update(viewers=0),lambda x:x['cases'][1].update(maxWrites=100000),lambda x:x['cases'][0].update(rate=0),lambda x:x['cases'][0].update(viewers=0),lambda x:x['cases'][0].update(id='../escape'),lambda x:x['cases'].append(copy.deepcopy(x['cases'][0])),lambda x:x.update(version=True)):
   bad=copy.deepcopy(cases());mutate(bad)
   with self.assertRaises(RuntimeError):protocol.binding({**b,'componentCases':bad},1000)
  self.assertIsNone(b.get('workload'));default=generator.traffic_commands('/synthetic',selected(),{'trafficRunId':'synthetic','settingsFingerprint':'a'*64},'test-k6',1)[0];self.assertEqual(default[default.index('--per')+1],'2');self.assertEqual(default[default.index('--probeEvery')+1],'300000')
 def test_command_builder_public_placement_and_independent_backgrounds(self):
  b=selected();descriptor={'trafficRunId':'synthetic-run','settingsFingerprint':'a'*64}
  for case in cases()['cases']:
   x=c.commands('/traffic',b,descriptor,case,'owned-k6',123)
   self.assertNotIn('--compose',x['probe']);self.assertEqual(x['probe'][x['probe'].index('--tenants')+1],'/traffic/components/'+case['id']+'/tenants.private.json');self.assertEqual(x['probe'][-2:],['--maxWrites',str(case['maxWrites'])]);self.assertEqual(x['inputScope']['stockClients'],16*case['viewers'])
   if case['kind']=='evrt':self.assertIsNone(x['k6']);self.assertEqual(x['inputScope']['ordinaryRestOfferedRps'],0)
   else:self.assertIn('OFFERED_RPS=180',x['k6']);self.assertIn('/traffic/tenants.private.json:/tenants.private.json:ro',x['k6']);self.assertIn('/traffic/components/rest-180/load:/out',x['k6']);self.assertIn('SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status',x['k6'])
 def test_sample_stable_and_phase_mismatch_refuses(self):
  rows=[{'id':str(i)}for i in range(1000)];self.assertEqual(len(c.selected(rows)),16);self.assertEqual(len({x['id']for x in c.selected(rows)}),16)
  a,b=cases()['cases'][:2];c.expect_payload(c.phase_payload(a),a)
  with self.assertRaises(RuntimeError):c.expect_payload(c.phase_payload(a),b)
 def test_missing_client_or_missing_counts_cannot_be_reduced_green(self):
  case=cases()['cases'][1];probe={'window':{'writes':{'ok':32,'failed':0},'expectedFrames':32,'deliveredFrames':32,'sockets':16,'connectedAtEnd':16}};complete={'verdict':'PASS','witnesses':[{'ready':True}]*32}
  self.assertEqual(c.reduce_case(case,probe,complete)['status'],'OBSERVED_SELECTED_CHAIN')
  broken=copy.deepcopy(probe);broken['window']['deliveredFrames']=31;self.assertEqual(c.reduce_case(case,broken,complete)['status'],'PARTIAL');self.assertEqual(c.reduce_case(case,probe,{'verdict':'PASS','witnesses':[]})['status'],'PARTIAL');self.assertEqual(c.reduce_case(case,probe,complete)['ordinaryREST'],{'measurement':'NOT_RUN'})
 def test_case_file_allowlist_excludes_k6_for_evrt_and_never_credentials(self):
  names=c.result_names(cases()['cases']);self.assertNotIn('components/evrt-v1/k6-summary.json',names);self.assertIn('components/rest-180/k6-summary.json',names);self.assertFalse(any('tenants' in n or'config'in n or'..'in n for n in names))
 def test_remote_receipt_cases_required_before_prepare(self):
  from test_parameters import extended,prep_args
  b=extended(1000,180,310,1);b['componentCases']=cases()
  with tempfile.TemporaryDirectory()as folder:
   args=prep_args(b,folder);bfile=Path(folder)/'binding.json';bfile.write_text(json.dumps(b))
   with patch.object(__import__('sys'),'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare:
    with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION'):cell.main()
    prepare.assert_not_called()
if __name__=='__main__':unittest.main()
