import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import api_cause as c

class ApiCause(unittest.TestCase):
 def fixture(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);d=Path(tmp.name)
  for name in c.FILES:
   p=d/'core'/name;p.parent.mkdir(parents=True,exist_ok=True)
   p.write_text("module.exports={createTenantApp(options){return options.exchange();},createOperatorApp(){}}; // admitRequest exchange\n" if name.endswith('index.js') else 'module.exports=()=>{};\n')
  (d/'state/ipc').mkdir(parents=True)
  config={'services':{'api':{'command':['node','deploy/multitenant/entrypoint.js','api']}}}
  m={'runPurpose':'discovery','profile':'pgstream-sample','owner':'a'*32,'pair':{'core':'b'*40},'generator':{'tools':{'node':{'path':shutil.which('node')}}}}
  return d,config,m
 def local_config(self,d,m):
  p=d/'local.json';p.write_text(json.dumps({'root':str(d/'core'),'out':str(d/'state/ipc/api-cause-api.json'),'owner':m['owner'],'source':m['pair']['core'],'sourceFiles':m['apiCause']['sourceFiles']}));return p
 def test_explicit_install_verify_refuse_config_source_mount_and_helper_changes(self):
  d,config,m=self.fixture();c.install(config,d,m);self.assertNotIn('apiCause',m);c.install(config,d,m,True);c.verify(config,d,m)
  for change in [lambda x:x['services']['api']['command'].pop(),lambda x:x['services']['api']['volumes'][0].update(read_only=False),lambda x:x['services']['api']['environment'].update(NODE_OPTIONS='--require other')]:
   b=copy.deepcopy(config);change(b)
   with self.assertRaisesRegex(RuntimeError,'M7_API_CAUSE_'):c.verify(b,d,m)
  without=copy.deepcopy(m);without.pop('apiCause')
  with self.assertRaisesRegex(RuntimeError,'RECORD_REQUIRED'):c.verify(config,d,without)
  p=d/'core'/c.FILES[0];p.write_text(p.read_text()+'// changed\n')
  with self.assertRaisesRegex(RuntimeError,'SOURCE_BYTES'):c.verify(config,d,m)
 def test_compose_inherited_null_commands_are_valid_with_and_without_observer(self):
  d,config,m=self.fixture();config['services']['nginx']={'command':None,'environment':None,'volumes':None}
  c.verify(config,d,m);c.install(config,d,m,True);c.verify(config,d,m)
  broken=copy.deepcopy(config);broken['services']['nginx']['environment']={'M7_API_CAUSE_CONFIG':'foreign'}
  with self.assertRaisesRegex(RuntimeError,'ROLES'):c.verify(broken,d,m)
  c.verify(config,d,m)

 def test_wrong_source_preload_refuses_before_actor_or_capture(self):
  d,config,m=self.fixture();c.install(config,d,m,True);f=self.local_config(d,m);(d/'core'/c.FILES[0]).write_text('changed')
  p=subprocess.run([shutil.which('node'),'--require',str(Path(c.__file__).with_name('api-cause-preload.cjs')),'-e','throw Error("ACTOR_MUST_NOT_START")'],env={'M7_API_CAUSE_CONFIG':str(f)},capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0);self.assertIn('M7_API_CAUSE_SOURCE_BYTES',p.stderr);self.assertNotIn('ACTOR_MUST_NOT_START',p.stderr);self.assertEqual(list((d/'state/ipc').iterdir()),[])
 def test_preload_is_lazy_restarts_distinct_and_failed_exchange_observed(self):
  d,config,m=self.fixture();c.install(config,d,m,True);f=self.local_config(d,m);helper=Path(c.__file__).with_name('api-cause-preload.cjs')
  # Lazy preload must not evaluate the source module.
  for _ in range(2):subprocess.run([shutil.which('node'),'--require',str(helper),'-e','void 0'],env={'M7_API_CAUSE_CONFIG':str(f)},capture_output=True,check=True)
  files=list((d/'state/ipc').glob('*.json.*.json'));self.assertEqual(len(files),2);self.assertEqual(len({json.loads(p.read_text())['instance'] for p in files}),2);self.assertTrue(all(not json.loads(p.read_text())['installed'] for p in files));self.assertEqual(c.retain(d,m)['verdict'],'UNMEASURED')
  for p in files:p.unlink()
  script="const m=require(process.argv[1]);const e=Object.assign(Error('DO_NOT_CAPTURE'),{code:'57014'});const app=m.createTenantApp({exchange(){throw e;},admitRequest(){}});"
  p=subprocess.run([shutil.which('node'),'--require',str(helper),'-e',script,str(d/'core'/c.FILES[0])],env={'M7_API_CAUSE_CONFIG':str(f)},capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0);files=list((d/'state/ipc').glob('*.json.*.json'));self.assertEqual(len(files),1);value=json.loads(files[0].read_text());self.assertEqual(value['events'],[{'stage':'exchange','code':'SQLSTATE_57014','count':1}]);self.assertNotIn('DO_NOT_CAPTURE',files[0].read_text());self.assertEqual(value['counters']['exchange']['thrown'],1)
 def test_scope_missing_capture_and_source_contract_refuse(self):
  d,config,m=self.fixture();m['runPurpose']='acceptance'
  with self.assertRaisesRegex(RuntimeError,'SCOPE'):c.install(config,d,m,True)
  m['runPurpose']='discovery';c.install(config,d,m,True);self.assertEqual(c.retain(d,m)['code'],'M7_API_CAUSE_NO_CAPTURE')

if __name__=='__main__':unittest.main()
