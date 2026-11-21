"""Immutable startup reuse controls; no Docker, SQL, application or traffic actor."""
import copy,json,os,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import adapter as a
import commissioning_wal as w
import run_configuration as rc
import runner

class StartupInheritance(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'runtime';self.root.mkdir();(self.root/'state').mkdir();self.compose=self.root/'frozen.compose.json';self.compose.write_text('{"services":{}}');(self.root/'env').write_text('SYNTHETIC=1\n')
  self.owner={'directory':str(self.root),'owner':'a'*32,'prepared':True,'project':'synthetic','pair':{'core':'b'*40,'deploy':'c'*40},'imageId':'sha256:'+'d'*64,'instrument':{'sha256':'e'*64},'profile':'pgstream-sample','runPurpose':'discovery','tenants':10000,'replicas':1,'tenantReadiness':'serve','platformStartup':{'kind':'admin-verification-v1','readiness':'serve','helperSha256':'f'*64},'composeSha256':w._digest(self.compose),'environmentSha256':w._digest(self.root/'env')}
  self.file=self.root/'owner.json';a.write(self.file,self.owner)
  self.args=SimpleNamespace(runtime_owner=str(self.file),state=str(self.root/'state'),compose=[str(self.compose)],env_file=str(self.root/'env'),tenant_readiness=None)
 def manifest(self):
  m={k:copy.deepcopy(v) for k,v in self.owner.items() if k not in (*w.STARTUP_FIELDS,'prepared')};m.update(attached=True,owner='1'*32);return m
 def inherit(self):
  m=self.manifest();w.inherit(self.args,m,self.owner,self.root);return m
 def test_inherit_exact_owner_selection_and_never_apply_on_attach(self):
  m=self.inherit();self.assertEqual(w.from_manifest(m),{});self.assertEqual(m['tenantReadiness'],'serve');self.assertEqual(m['platformStartup'],self.owner['platformStartup']);self.assertEqual(m['startupRuntimeOwner']['sha256'],a.digest(self.file));self.assertIn('tenant-readiness',runner.SESSION_PREPARE_ONLY)
  for key in ('tenant_readiness',):
   bad=copy.copy(self.args);setattr(bad,key,'all')
   with self.assertRaisesRegex(RuntimeError,'FRESH_PREPARE_ONLY'):w.inherit(bad,self.manifest(),self.owner,self.root)
 def test_foreign_owner_hash_image_state_compose_and_selector_refuse_restored(self):
  green=self.inherit()
  for mutate in (lambda m:m['startupRuntimeOwner'].update(sha256='0'*64),lambda m:m['startupRuntimeOwner'].update(owner='0'*32),lambda m:m.update(imageId='sha256:'+'0'*64),lambda m:m.update(tenantReadiness='all'),lambda m:m['platformStartup'].update(helperSha256='0'*64)):
   bad=copy.deepcopy(green);mutate(bad)
   with self.assertRaisesRegex(RuntimeError,'STARTUP_RUNTIME_'):w.from_manifest(bad)
  for field,value in [('state',str(self.root/'foreign')),('compose',[str(self.root/'foreign.json')]),('runtime_owner',str(self.root/'foreign.json'))]:
   args=copy.copy(self.args);setattr(args,field,value)
   with self.assertRaisesRegex(RuntimeError,'STARTUP_RUNTIME_BINDING'):w.inherit(args,self.manifest(),self.owner,self.root)
  original=self.compose.read_text();self.compose.write_text('{}')
  with self.assertRaisesRegex(RuntimeError,'STARTUP_RUNTIME_BINDING'):self.inherit()
  self.compose.write_text(original);self.assertEqual(w.from_manifest(self.inherit()),{})
 def test_unbound_attached_selection_still_refuses(self):
  m=self.manifest();m['tenantReadiness']='serve'
  with self.assertRaisesRegex(RuntimeError,'STARTUP_RUNTIME_OWNER_REQUIRED'):w.from_manifest(m)

CAPTURE=os.environ.get('M7_STARTUP_ATTACH_CAPTURE')
@unittest.skipUnless(CAPTURE,'retained actual startup capture explicitly required')
class RetainedStartup(unittest.TestCase):
 def setUp(self):
  self.capture=Path(CAPTURE);self.runtime=self.capture/'fixture';self.owner=a.document(self.runtime/'owner.json');self.config=a.document(self.capture/'config.json');self.receipt=a.document(Path(self.config['prepare']['receipt']));self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name);self.counter=0
  self.assertEqual(rc.sha(rc.from_manifest(self.owner)),self.receipt['configurationSha256']);self.assertEqual(self.owner['tenants'],10000);self.assertEqual(a.git(self.config['prepare']['core-repo'],'rev-parse','HEAD'),self.owner['pair']['core'])
 def arguments(self,config=None,receipt=None):
  config=copy.deepcopy(config or self.config);self.counter+=1;argv=['attach','--directory',str(self.out/('never-'+str(self.counter)))]
  if receipt is not None:
   file=self.out/('receipt-'+str(self.counter)+'.json');a.write(file,receipt);config['prepare']['receipt']=str(file)
  for k,v in config['prepare'].items():
   if k not in runner.SESSION_PREPARE_ONLY:argv+=['--'+k,str(v)]
  for k,v in {'project':self.owner['project'],'source-root':self.runtime/'core','state':self.runtime/'state','dependencies-root':self.runtime/'dependencies','env-file':self.runtime/'env','compose':self.runtime/'frozen.compose.json','runtime-owner':self.runtime/'owner.json'}.items():argv+=['--'+k,str(v)]
  return a.parser().parse_args(argv)
 def admission(self,args,inherit=None):
  # Original cleanup removed source/state/dependencies. Model only these two
  # pre-admission existence observations; never recreate/adopt the old fixture.
  # Git input comes from its actual unchanged ordinary source repository.
  original_dir=Path.is_dir;original_git=a.git;source=self.runtime/'core';state=self.runtime/'state';captured=[]
  def is_dir(path):return True if path in (source,state) else original_dir(path)
  def git(path,*argv):return original_git(self.config['prepare']['core-repo'],*argv) if Path(path)==source else original_git(path,*argv)
  def stop(m):captured.append(copy.deepcopy(m));raise RuntimeError('M7_CONTROL_ADMISSION_PASSED_BEFORE_ACTOR')
  with ExitStack() as stack:
   stack.enter_context(patch.object(Path,'is_dir',autospec=True,side_effect=is_dir));stack.enter_context(patch.object(a,'git',side_effect=git));stack.enter_context(patch.object(a,'instrument',return_value=copy.deepcopy(self.owner['instrument'])));image=stack.enter_context(patch.object(a,'image',side_effect=stop));resources=stack.enter_context(patch.object(a,'resources'))
   if inherit is not None:stack.enter_context(patch.object(w,'inherit',side_effect=inherit))
   try:a.attach(args)
   finally:resources.assert_not_called();self.assertFalse(Path(args.directory).exists())
  return captured
 def test_actual_two_field_omission_red_then_real_attach_admission_restored(self):
  args=self.arguments()
  with self.assertRaisesRegex(RuntimeError,'^M7_DIAGNOSTIC_CONFIGURATION_MISMATCH$'):self.admission(args,lambda *args:None)
  with self.assertRaisesRegex(RuntimeError,'ADMISSION_PASSED_BEFORE_ACTOR'):self.admission(self.arguments())
  for field,value in [('tenant_readiness','all')]:
   args=self.arguments();setattr(args,field,value)
   with self.assertRaisesRegex(RuntimeError,'FRESH_PREPARE_ONLY'):self.admission(args)
  with self.assertRaisesRegex(RuntimeError,'ADMISSION_PASSED_BEFORE_ACTOR'):self.admission(self.arguments())
 def test_actual_baseline_and_scale_cadences_bind_independent_receipts(self):
  for seconds,scale in [(1800,1),(310,2),(310,4),(310,1)]:
   config=copy.deepcopy(self.config);config['prepare'].update({'load-seconds':seconds,'workload-scale':scale});config['workSeconds']=7200
   with patch.object(a,'instrument',return_value=copy.deepcopy(self.owner['instrument'])):
    receipt=rc.resolve(config,{'status':'PENDING'})['diagnosticReceiptTemplate']
   receipt['status']='AUTHORIZED_DIAGNOSTIC';args=self.arguments(config,receipt)
   with self.assertRaisesRegex(RuntimeError,'ADMISSION_PASSED_BEFORE_ACTOR'):self.admission(args)
 def test_actual_foreign_image_state_and_bound_selector_tamper_refuse(self):
  args=self.arguments();args.image_id='sha256:'+'0'*64
  with self.assertRaisesRegex(RuntimeError,'RUNTIME_OWNER_MISMATCH'):self.admission(args)
  args=self.arguments();foreign=self.out/'foreign-state';foreign.mkdir();args.state=str(foreign)
  with self.assertRaisesRegex(RuntimeError,'STARTUP_RUNTIME_BINDING'):self.admission(args)
  actual=w.inherit
  for mutate,code in [(lambda m:m['startupRuntimeOwner'].update(sha256='0'*64),'STARTUP_RUNTIME_OWNER_CHANGED'),(lambda m:m.update(tenantReadiness='all'),'STARTUP_RUNTIME_SELECTION_MISMATCH'),(lambda m:m['platformStartup'].update(helperSha256='0'*64),'STARTUP_RUNTIME_SELECTION_MISMATCH')]:
   def tamper(args,m,runtime,root):actual(args,m,runtime,root);mutate(m)
   with self.assertRaisesRegex(RuntimeError,code):self.admission(self.arguments(),tamper)
  with self.assertRaisesRegex(RuntimeError,'ADMISSION_PASSED_BEFORE_ACTOR'):self.admission(self.arguments())
 def test_actual_startup_helper_proof_and_frozen_serving_readiness(self):
  helper=a.command(['git','-C',self.config['prepare']['deploy-repo'],'show',self.owner['pair']['deploy']+':bindings/compose/multitenant/platform-startup.js'],binary=True)
  root=self.out/'source-proof';file=root/'core/deploy/multitenant/platform-startup.js';file.parent.mkdir(parents=True);file.write_bytes(helper);self.assertEqual(a.digest(file),self.owner['platformStartup']['helperSha256'])
  a.platform_startup_config(a.document(self.runtime/'frozen.compose.json'),root,self.owner,verify=True)

if __name__=='__main__':unittest.main()
