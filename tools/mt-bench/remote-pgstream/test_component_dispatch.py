"""Actual optional session dispatch, with all actor/SQL/privilege seams mocked."""
import contextlib,copy,json,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import component_sessions as s,component_cases as c,protocol
from test_component_cases import cases,selected

def read(p):return json.loads(Path(p).read_text())
class Dispatch(unittest.TestCase):
 def test_actual_generator_dispatch_and_failure_cleanup_no_k6_evrt(self):
  for failure in(False,True):
   with tempfile.TemporaryDirectory()as folder:
    d=Path(folder);rows=[{'id':f'{i+1:08x}-1111-4111-8111-111111111111','host':'synthetic','token':'synthetic'}for i in range(1000)];protocol.write(d/'tenants.private.json',rows);b=selected();b.update(expiresAt=time.time()+10000,componentCases=cases());events=[];i=[0];current=[None]
    class Chan:
     def __init__(self,*args):pass
     def receive(self,kind,*args):
      return{}if kind=='finish'else c.phase_payload(b['componentCases']['cases'][i[0]])
     def send(self,kind,payload):
      events.append((kind,payload['caseId']))
      if kind=='client-complete':i[0]+=1
    def child(argv,*args):
     out=Path(argv[argv.index('--out')+1]).parent;case=b['componentCases']['cases'][i[0]];events.append(('launch',case['id']));current[0]=(out,case)
     def wait(**kw):
      protocol.write(out/'probe.json',{'clientWitnesses':[]});protocol.write(out/'fanout.json',{'probeWrites':{'byTenant':{}}});(out/'event-loop.jsonl').write_text('{}\n');return 0
     return types.SimpleNamespace(wait=wait,poll=lambda:0)
    def waitfile(path,probe,binding):
     out,case=current[0];Path(path).touch();protocol.write(out/'prime.json',{'primed':c.expected_clients(case)-(1 if failure and i[0]==1 else 0)})
    def run(argv,**kw):
     if argv[:3]==['docker','container','inspect']or argv[:2]==['docker','inspect']:return types.SimpleNamespace(returncode=1)
     case=b['componentCases']['cases'][i[0]];events.append(('k6',case['id']));out=d/'components'/case['id']/'load';protocol.write(out/'k6-summary.json',{'metrics':{}});return types.SimpleNamespace(returncode=0)
    def sample(process,binding,out,stop,name):protocol.write(out,{'complete':False,'samples':[]})
    g=types.SimpleNamespace(run_k6=lambda argv,d,b,name,output,timeout:run(argv),cleanup_k6=Mock(),GID=1001,UID=1001,child=child,restricted=lambda x:x,wait_file=waitfile,sample=sample,stop=Mock(),subprocess=types.SimpleNamespace(run=run))
    with patch.object(s,'Channel',Chan),patch.object(s.os,'chown'):
     if failure:
      with self.assertRaisesRegex(RuntimeError,'PRIME_FAILED'):s.generator_session(d,b,{'trafficRunId':'synthetic-run','settingsFingerprint':'a'*64,'files':{'workload.js':'b'*64}},g)
     else:s.generator_session(d,b,{'trafficRunId':'synthetic-run','settingsFingerprint':'a'*64,'files':{'workload.js':'b'*64}},g)
    g.stop.assert_called_once();self.assertEqual([x for k,x in events if k=='k6'],['rest-180'])
    if not failure:self.assertEqual([x for k,x in events if k=='client-complete'],[x['id']for x in cases()['cases']])
 def test_actual_sut_dispatch_brackets_and_final_transfer_seam(self):
  import component_sut
  with tempfile.TemporaryDirectory()as folder:
   d=Path(folder);b=selected();b['componentCases']=cases();m={'orchestrationHome':str(d.resolve()),'owner':'synthetic','pair':b['pair'],'imageId':b['imageId'],'tenants':1000,'cadence':{'loadSeconds':310}};events=[];i=[0]
   class Chan:
    def __init__(self,*args):pass
    def send(self,kind,payload):
     events.append(kind)
     if kind=='server-recovery-complete':i[0]+=1
    def receive(self,kind,*args):
     if kind=='finish':
      protocol.write(d/'components/generator-provenance.json',{'binding':b})
      for case in b['componentCases']['cases']:
       out=d/'components'/case['id']/'load';protocol.write(out/'probe.json',{'window':{'writes':{'ok':case['maxWrites'],'failed':0},'sockets':c.expected_clients(case),'connectedAtEnd':c.expected_clients(case),'expectedFrames':case['maxWrites']*case['viewers'],'deliveredFrames':case['maxWrites']*case['viewers']}});protocol.write(out/'generator-metrics.json',{'complete':False});
       if case['kind']=='rest':protocol.write(out/'k6-summary.json',{'metrics':{}})
      return{}
     case=b['componentCases']['cases'][i[0]];return{**c.phase_payload(case),**({'primed':c.expected_clients(case)}if kind=='client-primed'else{})}
   def snap(root,manifest,case,out):protocol.write(out,{'sampleTenants':16})
   def cost(root,out,which):events.append('cost-'+which);protocol.write(out/(which+'-cgroups.json'),{'roles':{},'at':1 if which=='before'else 2})
   a=types.SimpleNamespace(document=read,write=protocol.write,sample_context=Mock(),psql=Mock(),sampling=lambda *args:contextlib.nullcontext(),phase_snapshot=cost,verify=Mock());app=types.SimpleNamespace(a=a,idle=Mock(),load=Mock())
   with patch.object(s,'Channel',Chan),patch.object(component_sut,'snapshot',side_effect=snap),patch.object(component_sut,'completed',side_effect=lambda view,cm,case:{'verdict':'PASS','witnesses':[{'ready':True}]*case['maxWrites']}),patch.object(component_sut,'counts',return_value={'verdict':'GREEN','uncertain':0}):s.app_session(d,m,b,app)
   result=read(d/'component-summary.json');self.assertEqual(result['verdict'],'PARTIAL');self.assertEqual(len(result['cases']),4);self.assertEqual(events.count('cost-before'),4);self.assertEqual(events.count('cost-after'),4);self.assertEqual(app.load.call_count,4);self.assertEqual(a.verify.call_count,4)
if __name__=='__main__':unittest.main()
