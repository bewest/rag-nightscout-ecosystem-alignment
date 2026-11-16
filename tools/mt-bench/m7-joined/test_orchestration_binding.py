"""Actual command/custody code; every Docker effect is injected."""
import copy,datetime,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import orchestration_binding as b
class Fixture:
 def __init__(self,root):
  self.root=Path(root);self.state=self.root/'state';self.state.mkdir();self.project='synthetic-b';self.owner='a'*32;self.attempt='b'*32;self.pair={'core':'1'*40,'deploy':'2'*40};self.newpair={'core':'3'*40,'deploy':'4'*40};self.owner_file=self.root/'owner.json';self.env=self.root/'env';self.oldfile=self.root/'original.json';self.newfile=self.root/'candidate.json';self.journal=self.root/'journal.json';self.env.write_text('NS_DEMO_PROJECT='+self.project+'\nSECRET=private\n')
  def config(image,pair):
   roles={r:{'image':image if r!='postgres'else'sha256:'+'9'*64,'command':['node','old-'+r]if r!='postgres'else['postgres'],'labels':{b.OWNER:self.owner},'environment':{'NS_SOURCE_COMMIT':pair['core'],'NS_DEPLOY_COMMIT':pair['deploy']}if r!='postgres'else{},'volumes':[{'type':'bind','source':str(self.state/r),'target':'/state','read_only':False}],'networks':{'backend':None}}for r in('api','realtime','postgres')};return {'name':self.project,'services':roles,'networks':{'backend':{'name':self.project+'_backend'}}}
  self.old=config('sha256:'+'5'*64,self.pair);self.new=config('sha256:'+'6'*64,self.newpair)
  for r in('api','realtime'):self.new['services'][r]['command']=['node','new-'+r]
  self.new=b.stamp_candidate(self.new,self.attempt,['api','realtime']);self.oldfile.write_text(json.dumps(self.old));self.newfile.write_text(json.dumps(self.new));self.owner_file.write_text(json.dumps({'owner':self.owner,'project':self.project,'pair':self.pair,'imageId':'sha256:'+'5'*64,'composeSha256':b.digest(self.oldfile),'environmentSha256':b.digest(self.env)}));self.binding=self.bind()
 def bind(self):
  def epoch(file,cfg,pair):return {'configFile':str(file),'imageIds':{r:v['image']for r,v in cfg['services'].items()},'appRoles':['api','realtime'],'pair':pair}
  return b.make_binding(self.owner_file,self.env,{'original':epoch(self.oldfile,self.old,self.pair),'candidate':epoch(self.newfile,self.new,self.newpair)},'candidate',self.state,self.attempt)
 def row(self,role,epoch='original',cid=None):
  cfg=self.old if epoch=='original'else self.new;pair=self.pair if epoch=='original'else self.newpair;file=self.oldfile if epoch=='original'else self.newfile;spec=cfg['services'][role];labels={**spec['labels'],b.PROJECT:self.project,b.SERVICE:role,b.CONFIG_FILES:str(file)}
  if role!='postgres':labels.update({'org.opencontainers.image.revision':pair['core'],'org.nightscout.deploy.revision':pair['deploy']})
  return {'Id':cid or({'api':'a','realtime':'c','postgres':'d'}[role]*64),'Created':'2020-01-01T00:00:00Z','Image':spec['image'],'Config':{'Image':spec['image'],'Cmd':spec['command'],'Labels':labels,'Env':[k+'='+v for k,v in spec['environment'].items()]},'State':{'Running':True,'Pid':123},'HostConfig':{'Tmpfs':{}},'Mounts':[{'Type':'bind','Source':str(self.state/role),'Destination':'/state','RW':True}],'NetworkSettings':{'Networks':{self.project+'_backend':{}}}}
 def start(self):
  d=Docker(self);b.begin_journal(self.binding,list(d.rows.values()),self.journal);return d
class Docker:
 def __init__(self,f):self.f=f;self.rows={x['Id']:x for x in[f.row(r)for r in('api','realtime','postgres')]};self.effects=[];self.config_calls=0;self.override=None;self.failure=False
 def __call__(self,argv):
  argv=list(map(str,argv))
  if argv[:2]==['docker','compose']:
   if 'config'in argv:self.config_calls+=1;return json.dumps(self.override if self.override is not None else self.f.new if str(self.f.newfile)in argv else self.f.old)
   self.effects.append(argv);self.rows.pop('a'*64,None);row=self.f.row('api','candidate','e'*64);row['Created']=datetime.datetime.now(datetime.timezone.utc).isoformat();self.rows[row['Id']]=row
   if self.failure:raise OSError('synthetic-stdout-failed')
   return 'created'
  if argv[:3]==['docker','ps','-aq']:
   key=argv[-1]
   if key.startswith('id='):return key[3:]if key[3:]in self.rows else''
   if key.startswith('label='+b.PROJECT+'='):return '\n'.join(self.rows)
   return '\n'.join(x['Id']for x in self.rows.values()if x['Config']['Labels'].get(b.ATTEMPT)==self.f.attempt)
  if argv[:2]==['docker','inspect']:return json.dumps([self.rows[x]for x in argv[2:]if x in self.rows])
  if argv[:2]==['docker','stop']:
   self.effects.append(argv)
   for cid in argv[4:]:self.rows[cid]['State']['Running']=False
   return ''
  raise AssertionError('unexpected '+repr(argv[:3]))
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.f=Fixture(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_diagnostic_exact_memory_bytes_only(self):
  for service in self.f.new['services'].values():service.update(mem_limit=134217728,memswap_limit=134217728)
  self.f.newfile.write_text(json.dumps(self.f.new));owner=json.loads(self.f.owner_file.read_text());owner['diagnosticResources']={'selected':True};self.f.owner_file.write_text(json.dumps(owner));self.f.binding=self.f.bind()
  argv=b.compose_argv(self.f.binding,'up',['api'],['-d']);expanded=copy.deepcopy(self.f.new)
  for service in expanded['services'].values():service.update(mem_limit='134217728',memswap_limit='134217728')
  runner=lambda args:json.dumps(expanded)
  self.assertEqual(b.check_expanded(self.f.binding,argv,runner),expanded)
  for wrong in ('134217729','128m',True,134217728.0):
   broken=copy.deepcopy(expanded);broken['services']['api']['mem_limit']=wrong
   with self.assertRaisesRegex(RuntimeError,'EXPANDED_CONFIG_CHANGED'):b.check_expanded(self.f.binding,argv,lambda args:json.dumps(broken))
  for field,value in [('command',['node','changed']),('image','sha256:'+'8'*64),('environment',{'SECRET':'changed'})]:
   broken=copy.deepcopy(expanded);broken['services']['api'][field]=value
   with self.assertRaisesRegex(RuntimeError,'EXPANDED_CONFIG_CHANGED'):b.check_expanded(self.f.binding,argv,lambda args:json.dumps(broken))
  self.assertEqual(b.check_expanded(self.f.binding,argv,runner),expanded)
  del owner['diagnosticResources'];self.f.owner_file.write_text(json.dumps(owner));self.f.binding=self.f.bind();argv=b.compose_argv(self.f.binding,'up',['api'],['-d'])
  with self.assertRaisesRegex(RuntimeError,'EXPANDED_CONFIG_CHANGED'):b.check_expanded(self.f.binding,argv,runner)

 def mutate(self,d,**kw):return b.checked_run(self.f.binding,'up',['api'],d,lambda:None,self.f.journal,options=['-d','--no-build','--pull','never'],**kw)
 def test_named_source_run_stage_exact_suffix_and_profile(self):
  source=self.f.root/'producer.py';source.write_text('synthetic canonical producer')
  stages={'initialize':{'epoch':'candidate','argv':['--profile','ops','run','--rm','--no-deps','--pull','never','api','node','pool.js','initialize'],'sourceFile':str(source)}}
  def epoch(file,cfg,pair):return {'configFile':str(file),'imageIds':{r:v['image']for r,v in cfg['services'].items()},'appRoles':['api','realtime'],'pair':pair}
  binding=b.make_binding(self.f.owner_file,self.f.env,{'original':epoch(self.f.oldfile,self.f.old,self.f.pair),'candidate':epoch(self.f.newfile,self.f.new,self.f.newpair)},'candidate',self.f.state,self.f.attempt,run_stages=stages)
  opts=['--rm','--no-deps','--pull','never'];good=b.compose_argv(binding,'run',['api'],opts,stage='initialize');self.assertEqual(good[-4:],['api','node','pool.js','initialize'])
  for stage,role in [('unknown','api'),('initialize','realtime')]:
   with self.assertRaisesRegex(RuntimeError,'RUN_STAGE_'):b.compose_argv(binding,'run',[role],opts,stage=stage)
  source.write_text('changed')
  with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'):b.compose_argv(binding,'run',['api'],opts,stage='initialize')
  source.write_text('synthetic canonical producer');b.compose_argv(binding,'run',['api'],opts,stage='initialize')
 def oneoff(self):
  binding=copy.deepcopy(self.f.binding);binding.update(oneoffRoot=str(self.f.root),oneoffImages={'k6':'sha256:'+'8'*64});binding['sha256']=b.sha(b.encode({k:v for k,v in binding.items()if k!='sha256'}));self.f.binding=binding;d=self.f.start();attachment=self.f.root/'attachment';attachment.mkdir();(attachment/'owner.json').write_text(json.dumps({'owner':'7'*32,'project':binding['project'],'attached':True}));scope={'directory':str(attachment),'owner':'7'*32,'imageId':'sha256:'+'8'*64};argv=['docker','run','--rm','--network','none','--label',b.OWNER+'='+scope['owner'],'--label',b.PROJECT+'='+binding['project'],scope['imageId'],'version'];return binding,d,scope,argv
 def test_oneoff_wrong_image_owner_project_attempt_options_before_effect(self):
  binding,d,scope,argv=self.oneoff();effects=[]
  def runner(args):
   if args[:3]==['docker','image','inspect']:return json.dumps([{'Id':scope['imageId'],'Config':{'Cmd':None,'Entrypoint':['k6'],'Env':[],'User':''}}])
   if args[:2]==['docker','run']:effects.append(args);return 'k6'
   return d(args)
  for bad in [argv[:-2]+['sha256:'+'9'*64,'version'],[x.replace(scope['owner'],'f'*32)for x in argv],[x.replace(binding['project'],'wrong')for x in argv],argv[:3]+['--label',b.ATTEMPT+'=foreign']+argv[3:],argv[:3]+['--cidfile','/foreign']+argv[3:]]:
   with self.assertRaisesRegex(RuntimeError,'M7_BINDING_ONEOFF_'):b.checked_oneoff(binding,'k6-version',bad,scope,runner,lambda:True,self.f.journal)
   self.assertFalse(effects)
  b.checked_oneoff(binding,'k6-version',argv,scope,runner,lambda:True,self.f.journal);self.assertEqual(len(effects),1);self.assertIn('--cidfile',effects[0])
 def test_oneoff_exact_layout_attempt_and_foreign_cid_red_restore(self):
  binding,d,scope,argv=self.oneoff()
  meta=lambda args:json.dumps([{'Id':scope['imageId'],'Config':{'Entrypoint':['k6'],'Env':[],'User':''}}])
  cidfile=self.f.root/'exclusive.cid';intent=b._oneoff_intent(binding,'k6-version',argv,scope,meta,cidfile);layout=intent['layout'];row={'Id':'e'*64,'Created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'Image':scope['imageId'],'Config':{'Image':scope['imageId'],'Cmd':['version'],'Entrypoint':['k6'],'Env':[],'User':'','Labels':layout['labels']},'State':{'Running':True},'HostConfig':{'NetworkMode':'none','Tmpfs':{},'Privileged':False},'Mounts':[]}
  for mode in('attempt','owner','image','command','mount','env','cid'):
   bad=copy.deepcopy(row)
   if mode=='attempt':bad['Config']['Labels'][b.ATTEMPT]='f'*32
   if mode=='owner':bad['Config']['Labels'][b.OWNER]='f'*32
   if mode=='image':bad['Image']='sha256:'+'f'*64
   if mode=='command':bad['Config']['Cmd']=['run','foreign']
   if mode=='mount':bad['Mounts']=[{'Type':'bind','Source':'/foreign','Destination':'/out','RW':True}]
   if mode=='env':bad['Config']['Env']=['EXTRA=foreign']
   if mode=='cid':cidfile.write_text('f'*64)
   with self.assertRaisesRegex(RuntimeError,'M7_BINDING_ONEOFF_'):b.qualify_oneoff(binding,bad,intent)
   if cidfile.exists():cidfile.unlink()
  b.qualify_oneoff(binding,row,intent)
 def test_oneoff_cli_failure_captures_exact_nonce_and_cleanup_no_mutable_files(self):
  binding,d,scope,argv=self.oneoff()
  def runner(args):
   if args[:3]==['docker','image','inspect']:return json.dumps([{'Id':scope['imageId'],'Config':{'Entrypoint':['k6'],'Env':[],'User':''}}])
   if args[:2]==['docker','run']:
    intent=b.load(self.f.journal)['intents'][-1];layout=intent['layout'];row={'Id':'e'*64,'Created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'Image':scope['imageId'],'Config':{'Image':scope['imageId'],'Cmd':['version'],'Entrypoint':['k6'],'Env':[],'User':'','Labels':layout['labels']},'State':{'Running':True},'HostConfig':{'NetworkMode':'none','Tmpfs':{},'Privileged':False},'Mounts':[]};d.rows[row['Id']]=row;raise OSError('capture failed')
   return d(args)
  with self.assertRaises(OSError):b.checked_oneoff(binding,'k6-version',argv,scope,runner,lambda:True,self.f.journal)
  self.assertIn('e'*64,b.load(self.f.journal)['records']);self.f.env.write_text('broken');result=b.cleanup_recorded(self.f.journal,runner,lambda:True);self.assertIn('e'*64,result['stoppedIds'])
 def test_historical_ephemeral_uses_canonical_ops_profile(self):
  d=self.f.start();argv=b.compose_argv(self.f.binding,'run',['api'],['--rm','--no-deps','--pull','never'],epoch='original')
  self.assertEqual(argv[8:12],['--profile','ops','run','--rm'])
  self.assertEqual(argv[-1],'api');self.assertIn(b.ATTEMPT+'='+self.f.attempt,argv)
  # A completed --rm run can leave no live candidate; original custody remains.
  def completed(args):
   if args[:2]==['docker','compose']and 'config'not in args:d.effects.append(args);return 'existing-demo-unsealed'
   return d(args)
  b.checked_run(self.f.binding,'run',['api'],completed,lambda:None,self.f.journal,options=['--rm','--no-deps','--pull','never'],epoch='original')
  self.assertEqual(len(d.effects),1);self.assertEqual(len(b.load(self.f.journal)['records']),3)
 def test_wrong_actual_project_red_before_effect_restored_green(self):
  d=self.f.start();argv=b.compose_argv(self.f.binding,'up',['api'],['-d','--no-build','--pull','never']);argv[3]='synthetic-3k'
  with self.assertRaisesRegex(RuntimeError,'ACTUAL_ARGV_CHANGED'):self.mutate(d,actual_argv=argv)
  self.assertFalse(d.effects);self.mutate(d);self.assertEqual(len(d.effects),1)
 def test_expanded_owner_source_mount_project_red_before_effect(self):
  d=self.f.start()
  for field in('name','owner','source','mount'):
   cfg=copy.deepcopy(self.f.new)
   if field=='name':cfg['name']='wrong'
   if field=='owner':cfg['services']['api']['labels'][b.OWNER]='f'*32
   if field=='source':cfg['services']['api']['environment']['NS_SOURCE_COMMIT']='f'*40
   if field=='mount':cfg['services']['api']['volumes'][0]['source']='/foreign/state'
   d.override=cfg
   with self.assertRaisesRegex(RuntimeError,'EXPANDED_'):self.mutate(d)
   self.assertFalse(d.effects)
  d.override=None;self.mutate(d)
 def test_owner_env_config_tamper_red_before_effect_restored(self):
  d=self.f.start()
  for file in(self.f.owner_file,self.f.env,self.f.newfile):
   raw=file.read_bytes();file.write_bytes(raw+b'\n')
   with self.assertRaisesRegex(RuntimeError,'BINDING_'):self.mutate(d)
   self.assertFalse(d.effects);file.write_bytes(raw)
  self.mutate(d)
 def test_missing_canonical_anchor_has_no_owner_fallback(self):
  cfg=copy.deepcopy(self.f.old);cfg.pop('name');self.f.oldfile.write_text(json.dumps(cfg))
  with self.assertRaisesRegex(RuntimeError,'PROJECT_MISMATCH'):b.canonical_project({'project':self.f.project},self.f.env,self.f.oldfile)
  self.f.oldfile.write_text(json.dumps(self.f.old));self.f.env.write_text('OTHER=synthetic\n')
  with self.assertRaisesRegex(RuntimeError,'ENV_PROJECT_REQUIRED'):b.canonical_project({'project':self.f.project},self.f.env,self.f.oldfile)
 def test_attempt_omission_swapped_nonce_and_foreign_state_red(self):
  original=self.f.newfile.read_bytes()
  for mode in('missing','swap','state'):
   cfg=json.loads(original)
   if mode=='missing':
    for r in('api','realtime'):cfg['services'][r]['labels'].pop(b.ATTEMPT)
   if mode=='swap':
    for r in('api','realtime'):cfg['services'][r]['labels'][b.ATTEMPT]='f'*32
   if mode=='state':cfg['services']['api']['volumes'][0]['source']='/foreign/state'
   self.f.newfile.write_text(json.dumps(cfg));self.f.new=cfg
   with self.assertRaisesRegex(RuntimeError,'ATTEMPT|STATE'):self.f.bind()
  self.f.newfile.write_bytes(original);self.f.new=json.loads(original);self.f.bind()
 def test_cleanup_old_epoch_and_new_epoch_without_mutable_project(self):
  d=self.f.start();self.mutate(d);self.f.owner_file.write_text('{}');self.f.env.write_text('broken');self.f.newfile.write_text('{}');result=b.cleanup_recorded(self.f.journal,d,lambda:None)
  self.assertEqual(result['status'],'EXACT_RECORDED_IDS_STOPPED');self.assertFalse(d.rows['c'*64]['State']['Running']);self.assertFalse(d.rows['e'*64]['State']['Running']);self.assertFalse(result['mutableDeclarationRead'])
 def test_stdout_failure_still_records_and_stops_created_ids(self):
  d=self.f.start();d.failure=True
  with self.assertRaises(OSError):self.mutate(d)
  self.assertIn('e'*64,b.cleanup_recorded(self.f.journal,d,lambda:None)['stoppedIds'])
 def test_post_capture_failure_recovers_from_attempt_intent(self):
  d=self.f.start()
  with patch.object(b,'record_created',side_effect=RuntimeError('synthetic-capture-failed')):
   with self.assertRaisesRegex(RuntimeError,'capture-failed'):self.mutate(d)
  self.assertIn('e'*64,b.cleanup_recorded(self.f.journal,d,lambda:None)['stoppedIds'])
 def test_journal_write_failure_does_not_skip_owned_cleanup(self):
  d=self.f.start();self.mutate(d)
  with patch.object(b,'_save',side_effect=OSError('disk-failed')):result=b.cleanup_recorded(self.f.journal,d,lambda:None)
  self.assertFalse(result['journalPersisted']);self.assertIn('e'*64,result['stoppedIds'])
 def test_foreign_attempt_owner_refused_while_ours_stops(self):
  d=self.f.start();self.mutate(d);foreign=self.f.row('api','candidate','f'*64);foreign['Config']['Labels'][b.OWNER]='f'*32;foreign['Created']=datetime.datetime.now(datetime.timezone.utc).isoformat();d.rows[foreign['Id']]=foreign;result=b.cleanup_recorded(self.f.journal,d,lambda:None)
  self.assertEqual(result['status'],'OWNED_STOPPED_FOREIGN_REFUSED');self.assertTrue(d.rows['f'*64]['State']['Running']);self.assertFalse(d.rows['e'*64]['State']['Running'])
 def test_changed_recorded_layout_refuses_foreign_id_without_broad_stop(self):
  d=self.f.start();d.rows['c'*64]['Config']['Cmd']=['node','new-realtime'];result=b.cleanup_recorded(self.f.journal,d,lambda:None);self.assertIn('M7_BINDING_ROLE_COMMAND_CHANGED',result['refusals']);self.assertTrue(d.rows['c'*64]['State']['Running']);self.assertFalse(d.rows['d'*64]['State']['Running'])
 def test_only_new_declarations_get_unique_attempt_label(self):
  self.assertNotIn(b.ATTEMPT,self.f.old['services']['api']['labels']);self.assertEqual(self.f.new['services']['api']['labels'][b.ATTEMPT],self.f.attempt)
 def test_cheap_read_prefix_and_embedded_namespace_override_refusal(self):
  d=self.f.root/'fixture';d.mkdir();(d/'env').write_bytes(self.f.env.read_bytes());(d/'frozen.compose.json').write_bytes(self.f.oldfile.read_bytes());m=json.loads(self.f.owner_file.read_text());(d/'owner.json').write_text(json.dumps(m));self.assertEqual(b.fixture_argv(d,['exec','-T','postgres','psql','-f','some.sql'])[3],self.f.project)
  with self.assertRaisesRegex(RuntimeError,'ARGV_OVERRIDE'):b.fixture_argv(d,['up','-p','wrong','api'])
  m['project']='wrong';(d/'owner.json').write_text(json.dumps(m))
  with self.assertRaisesRegex(RuntimeError,'PROJECT_MISMATCH'):b.fixture_argv(d,['exec','-T','postgres','psql'])
 def test_null_command_resolves_exact_image_default_not_observed_runtime(self):
  cfg=copy.deepcopy(self.f.old);cfg['services']['postgres']['command']=None
  meta={'Id':cfg['services']['postgres']['image'],'Config':{'Cmd':['postgres'],'Entrypoint':['entrypoint.sh']}}
  value=b._layout(cfg,'postgres',meta['Id'],[],self.f.pair,str(self.f.state),[str(self.f.oldfile)],meta)
  self.assertEqual(value['command'],['postgres']);self.assertEqual(value['entrypoint'],['entrypoint.sh'])
  with self.assertRaisesRegex(RuntimeError,'IMAGE_COMMAND_REQUIRED'):b._layout(cfg,'postgres',meta['Id'],[],self.f.pair,str(self.f.state),[str(self.f.oldfile)])
  bad=copy.deepcopy(meta);bad['Id']='sha256:'+'f'*64
  with self.assertRaisesRegex(RuntimeError,'IMAGE_METADATA_CHANGED'):b._layout(cfg,'postgres',meta['Id'],[],self.f.pair,str(self.f.state),[str(self.f.oldfile)],bad)
 def test_unknown_no_attempt_id_is_refused_without_stopping_it(self):
  d=self.f.start();foreign=self.f.row('api','original','f'*64);d.rows[foreign['Id']]=foreign
  result=b.cleanup_recorded(self.f.journal,d,lambda:None)
  self.assertIn('M7_BINDING_UNRECORDED_PROJECT_ID',result['refusals']);self.assertTrue(d.rows['f'*64]['State']['Running']);self.assertFalse(d.rows['a'*64]['State']['Running'])
 def test_created_row_omission_or_swap_attempt_is_not_owned(self):
  for value in(None,'f'*32):
   row=self.f.row('api','candidate','e'*64)
   if value is None:row['Config']['Labels'].pop(b.ATTEMPT)
   else:row['Config']['Labels'][b.ATTEMPT]=value
   with self.assertRaisesRegex(RuntimeError,'ATTEMPT_CHANGED'):b.qualify_row(self.f.binding,row,'candidate',created=True)
 def test_recorded_id_actions_render_exact_epoch_and_refuse_unknown(self):
  d=self.f.start()
  with self.assertRaisesRegex(RuntimeError,'UNRECORDED_ID'):b.checked_ids(self.f.journal,'start',['f'*64],d,lambda:None)
  self.assertFalse(d.effects)
  b.checked_ids(self.f.journal,'stop',['c'*64],d,lambda:None);self.assertFalse(d.rows['c'*64]['State']['Running']);self.assertEqual(d.config_calls,1)
 def test_bare_option_service_and_false_authorizer_refuse_before_effect(self):
  d=self.f.start()
  with self.assertRaisesRegex(RuntimeError,'OPTION_REFUSED'):b.checked_run(self.f.binding,'up',['api'],d,lambda:None,self.f.journal,options=['never'])
  with self.assertRaisesRegex(RuntimeError,'AUTHORIZER_REFUSED'):b.checked_run(self.f.binding,'up',['api'],d,lambda:False,self.f.journal)
  self.assertFalse(d.effects)
 def test_cleanup_discovery_failure_still_stops_previously_recorded_ours(self):
  d=self.f.start();self.mutate(d);original=d.__call__
  def fail_discovery(argv):
   if argv[:3]==['docker','ps','-aq']and str(argv[-1]).startswith('label='+b.ATTEMPT+'='):raise OSError('synthetic-discovery-failed')
   return original(argv)
  result=b.cleanup_recorded(self.f.journal,fail_discovery,lambda:None)
  self.assertIn('M7_BINDING_DISCOVERY_UNAVAILABLE',result['refusals']);self.assertFalse(d.rows['e'*64]['State']['Running'])
 def test_instrument_inventory_missing_shared_module_refuses(self):
  import adapter
  current=['tools/mt-bench/m7-joined/adapter.py','tools/mt-bench/m7-joined/orchestration_binding.py']
  def git(repo,*args):
   if args==('rev-parse','HEAD'):return 'a'*40
   if args[0]=='ls-files':return '\n'.join(current)
   if args[0]=='diff':return ''
   raise AssertionError(args)
  with patch.object(adapter,'git',side_effect=git):
   current.pop()
   with self.assertRaisesRegex(RuntimeError,'ORCHESTRATION_BINDING_NOT_COMMITTED'):adapter.instrument()
   current.append('tools/mt-bench/m7-joined/orchestration_binding.py');self.assertIn(current[-1],adapter.instrument()['files'])
 def test_finite_authorizer_refusal_never_mutates(self):
  d=self.f.start()
  def refused():raise RuntimeError('EXPIRED_FINITE_GO')
  with self.assertRaisesRegex(RuntimeError,'EXPIRED'):b.checked_run(self.f.binding,'up',['api'],d,refused,self.f.journal)
  self.assertFalse(d.effects)
if __name__=='__main__':unittest.main()
