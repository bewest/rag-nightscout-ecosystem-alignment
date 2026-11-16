"""JWT setup selection through paired remote admission and launch custody."""
import copy,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app,cell,generator,protocol,transport
import test_discovery_source as discovery_controls
import test_driver_actor as actor_controls
ROOT=Path(__file__).resolve().parents[3]
SETUP=r'''
const fs=require('node:fs'),vm=require('node:vm');const [file,concurrency]=process.argv.slice(1),batches=[],requests=[];
const tenants=Array.from({length:33},(_,i)=>({id:String(i),host:'synthetic.invalid',token:String(i)}));
const respond=url=>{const i=Number(url.split('/').pop());requests.push(i);return{status:200,body:JSON.stringify({token:'synthetic-'+i})}};
const c={__VU:0,__ENV:{TENANTS_FILE:'unused',BASE_URL:'http://synthetic.invalid',JWT_SETUP_CONCURRENCY:concurrency,SHAPES:'w_treatments_v3'},SharedArray:function(n,f){return f()},open:()=>JSON.stringify(tenants),exec:{},sha256:()=>'',Counter:class{add(){}},console:{log(){}},http:{get:respond,batch:rows=>{batches.push(rows.length);return rows.map(r=>respond(r.url))}}};
vm.createContext(c);let source=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
const data=vm.runInContext(source+'\nsetup();',c);console.log(JSON.stringify({requests,batches,jwts:data.jwts}));
'''
class JwtSetup(unittest.TestCase):
 def selected(self,value=None):
  b=discovery_controls.DiscoverySource().request()
  if value is not None:b['workload']['jwtSetupConcurrency']=value
  return b
 def test_default_range_and_actual_setup_dispatch_count(self):
  from workload import generate
  for value in (None,1,16,64):
   b=self.selected(value);protocol.binding(b);expected=value or 1
   _,argv=generator.traffic_commands('/synthetic',b,{'trafficRunId':'synthetic','settingsFingerprint':'f'*64},'synthetic',0)
   self.assertEqual([x for x in argv if str(x).startswith('JWT_SETUP_CONCURRENCY=')],['JWT_SETUP_CONCURRENCY='+str(expected)])
   with tempfile.TemporaryDirectory()as tmp:
    target=Path(tmp)/'workload.js';generate(ROOT,target)
    r=json.loads(subprocess.check_output(['node','-e',SETUP,str(target),str(expected)],text=True,timeout=10))
   self.assertEqual(r['requests'],list(range(33)));self.assertEqual(r['jwts'],['synthetic-'+str(i)for i in range(33)])
   self.assertEqual(r['batches'],[]if expected==1 else[min(expected,33-i)for i in range(0,33,expected)])
  for bad in (0,65,True,16.5,'16',None):
   b=self.selected();b['workload']['jwtSetupConcurrency']=bad
   with self.assertRaisesRegex(RuntimeError,'JWT_SETUP_CONCURRENCY'):protocol.binding(b)
 def test_source_provenance_break_and_restore(self):
  here=Path(__file__).resolve().parent;expected=protocol.source_identity(here)
  for name in ('protocol.py','cell.py','transport.py','generator.py'):self.assertIn(name,expected['files'])
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp)
   for name in expected['files']:(d/name).write_bytes((here/name).read_bytes())
   self.assertEqual(protocol.source_identity(d),expected)
   target=d/'generator.py';original=target.read_bytes();target.write_bytes(original+b'\n# synthetic source drift\n')
   self.assertNotEqual(protocol.source_identity(d)['sha256'],expected['sha256'])
   target.write_bytes(original);self.assertEqual(protocol.source_identity(d),expected)
 def test_dropped_altered_duplicate_env_and_captured_env_refuse(self):
  c=actor_controls.Actor();c.setUp()
  try:
   b=self.selected(16);b.update({k:c.b[k]for k in ('nonce','k6Image','sourceSha256')});c.b=b
   args=generator.traffic_commands(c.d,b,{'trafficRunId':'synthetic','settingsFingerprint':'f'*64},c.name,0)[1];i=args.index('JWT_SETUP_CONCURRENCY=16')
   for broken in (args[:i-1]+args[i+1:],args[:i]+['JWT_SETUP_CONCURRENCY=1']+args[i+1:],args[:i+1]+['-e','JWT_SETUP_CONCURRENCY=16']+args[i+1:],args[:i+1]+['--env=JWT_SETUP_CONCURRENCY=1']+args[i+1:],args[:i+1]+['--env','JWT_SETUP_CONCURRENCY=1']+args[i+1:]):
    with c.seams(),self.assertRaisesRegex(RuntimeError,'JWT_SETUP_CHANGED'):generator.plan_k6(broken,c.d,b,c.name)
    self.assertFalse(generator.actor_files(c.d,c.name)[0].exists())
   with c.seams():generator.plan_k6(args,c.d,b,c.name);c.create()
   intent=json.loads(generator.actor_files(c.d,c.name)[0].read_text());self.assertEqual(intent['environment']['JWT_SETUP_CONCURRENCY'],'16')
   original=copy.deepcopy(c.rows[c.cid]);row=c.rows[c.cid];row['Config']['Env']=[x.replace('JWT_SETUP_CONCURRENCY=16','JWT_SETUP_CONCURRENCY=1')for x in row['Config']['Env']]
   with self.assertRaisesRegex(RuntimeError,'ENVIRONMENT'):generator.qualify_k6(row,intent)
   self.assertEqual(generator.qualify_k6(original,intent),c.cid)
  finally:c.tmp.cleanup()
 @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired controller root required')
 def test_actual_node_validate_caller_worker_cell_admission(self):
  controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT']).resolve();loader=importlib.util.spec_from_file_location('jwt_controller_worker',controller/'tools/perf-cloud/pgstream-worker.py');w=importlib.util.module_from_spec(loader);loader.loader.exec_module(w)
  for selection in (None,16):
   b=self.selected(selection);expected=selection or 1;protocol.binding(b)
   hosts={r:{**h,'privateIPv4':b['appAddress']if r=='sut'else b['generatorAddress'],'networkBitsPerSecond':1000000000,'allocationSource':'provider-inventory','headroom':{'measurement':'UNMEASURED'}}for r,h in b['workload']['resourcePlan']['hosts'].items()}
   receipt={'kind':'joined-diagnostic','status':'AUTHORIZED_DIAGNOSTIC','functionalAcceptanceAtAuthorization':'PENDING','imageId':b['imageId'],'pair':b['pair'],'instrument':'c'*64,'limits':{'tenants':b['tenants'],'apiReplicas':1,'trafficSeconds':b['workload']['cadence']['loadSeconds']},'remoteProfile':b['profile'],'remoteTransport':b['transport'],'remoteExtensionSha256':b['sourceSha256'],'completionContract':'evaluator-work-v2','remoteWorkload':b['workload'],'remoteReportMode':'discovery'}
   spec={'profile':b['profile'],'reportMode':'discovery','runId':b['runId'],'cloudId':b['cloudId'],'nonce':b['nonce'],'tenants':b['tenants'],'logicalPollingClients':b['workload']['resourcePlan']['logicalPollingClients'],'pins':{**b['pair'],'app':b['imageId'],'postgres':transport.POSTGRES},'cadence':b['workload']['cadence'],'primerConcurrency':b['workload']['primerConcurrency'],'resourcePlan':b['workload']['resourcePlan'],'hosts':hosts,'port':b['port'],'expiresAt':b['expiresAt'],'k6Image':b['k6Image'],'extensionSha256':b['sourceSha256'],'helperCommit':'b'*40,'transport':b['transport'],'completionContract':'evaluator-work-v2','diagnostics':'off','receipt':receipt,'sourceQualification':{'path':'/synthetic/proof.json','sha256':'e'*64},'controllerIPv4':'192.0.2.1','sutInbound':[{'protocol':'tcp','port':22,'sourceIPv4':'192.0.2.1'},{'protocol':'tcp','port':b['port'],'sourceIPv4':b['generatorAddress'],'sourceProviderId':hosts['driver']['providerId']}],'driverLimits':{'fdSoft':65536,'fdHard':65536,'k6PreallocatedVUsFormula':'min(400,ceil(rate*1000/arrivalCycleMs)*2+5)','k6MaxVUsPerScenario':800,'measurement':'UNMEASURED'},'pgstreamProducer':'canonical-262-with-pool-initialize','providerTokenOnHosts':False}
   if selection is not None:spec['jwtSetupConcurrency']=selection
   js="import {validate} from "+json.dumps((controller/'tools/perf-cloud/pgstream-calibration.mjs').as_uri())+";import {runtimeBinding} from "+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+";let s='';for await(const c of process.stdin)s+=c;const v=JSON.parse(s);validate(v);console.log(JSON.stringify(runtimeBinding(v)));"
   def bind(s):return subprocess.run(['node','--input-type=module','-e',js],input=json.dumps(s),capture_output=True,text=True,timeout=10)
   result=bind(spec);self.assertEqual(result.returncode,0,result.stderr);actual=json.loads(result.stdout);self.assertEqual(actual,b)
   for invalid in (0,65,True,16.5,'16',None):
    bad=copy.deepcopy(spec);bad['jwtSetupConcurrency']=invalid;refused=bind(bad);self.assertNotEqual(refused.returncode,0);self.assertIn('PGCAL_JWT_SETUP_CONCURRENCY',refused.stderr)
   if selection:
    for mutate in (lambda s:s.pop('jwtSetupConcurrency'),lambda s:s.update(jwtSetupConcurrency=1),lambda s:s['receipt']['remoteWorkload'].update(jwtSetupConcurrency=1)):
     broken=copy.deepcopy(spec);mutate(broken);self.assertNotEqual(bind(broken).returncode,0)
   with tempfile.TemporaryDirectory()as tmp:
    d=Path(tmp);(d/'input').mkdir();(d/'input/binding.json').write_text(json.dumps(actual));r=d/'input/receipt.json';r.write_text(json.dumps(receipt))
    with patch.object(w,'ROOT',d):argv=list(map(str,w.prepare_arguments(spec)))[2:]
    self.assertEqual(argv[argv.index('--jwt-setup-concurrency')+1],str(expected))
    def admit(args):
     with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare')as prepare,patch.object(app,'record_prepared_binding'):
      cell.main();return prepare.call_args.args[0]
    parsed=admit(argv);self.assertEqual(parsed.jwt_setup_concurrency,expected)
    m={'pair':b['pair'],'imageId':b['imageId'],'postgresImageId':transport.POSTGRES,'tenants':b['tenants'],'replicas':1,'profile':'pgstream-sample','runPurpose':'discovery','completionContract':'evaluator-work-v2','cadence':app.a.cadence_options(parsed),'primerConcurrency':parsed.primer_concurrency,'jwtSetupConcurrency':parsed.jwt_setup_concurrency};transport.cell_contract(m,b)
    if selection:
     i=argv.index('--jwt-setup-concurrency')
     for broken in (argv[:i]+argv[i+2:],argv[:i+1]+['1']+argv[i+2:]):
      with self.assertRaisesRegex(RuntimeError,'PREPARE_PROFILE_REQUIRED'):admit(broken)
     with self.assertRaisesRegex(RuntimeError,'EXPLICIT_CADENCE_REQUIRED'):transport.cell_contract({**m,'jwtSetupConcurrency':1},b)
     bad=copy.deepcopy(receipt);bad['remoteWorkload']['jwtSetupConcurrency']=1;r.write_text(json.dumps(bad))
     with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION_REQUIRED'):admit(argv)
     r.write_text(json.dumps(receipt));self.assertEqual(admit(argv).jwt_setup_concurrency,16)
if __name__=='__main__':unittest.main()
