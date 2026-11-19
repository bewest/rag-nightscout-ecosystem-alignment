"""Source-owned Compose binding and exact-ID custody, outside timing/PID policy.

A caller supplies its existing finite authorizer. No shell/ambient Compose array is
accepted. Read/SQL calls use only the cheap immutable prefix; checked mutations
also render actual Compose config and write intent before effect. Raw configs and
environments remain private; journal layouts retain hashes, never env values.
"""
from pathlib import Path
import copy,datetime,hashlib,json,os,re,time
import workload_inputs
from contract import require,OWNER
ATTEMPT='org.nightscout.m7.attempt'
PROJECT='com.docker.compose.project'
SERVICE='com.docker.compose.service'
CONFIG_FILES='com.docker.compose.project.config_files'
HEX=re.compile(r'[a-f0-9]{64}')
IMAGE=re.compile(r'sha256:[a-f0-9]{64}')
NAME=re.compile(r'[a-z0-9][a-z0-9_-]{0,62}')

def sha(value):return hashlib.sha256(value).hexdigest()
def digest(path):return sha(Path(path).read_bytes())
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def load(path):return json.loads(Path(path).read_text())
def _absolute(path):
 p=Path(path);require(p.is_absolute(),'M7_BINDING_ABSOLUTE_PATH_REQUIRED');return str(p.resolve())
def _environment_project(path):
 values=[line.split('=',1)[1].strip()for line in Path(path).read_text().splitlines()if line.startswith('NS_DEMO_PROJECT=')]
 require(len(values)==1,'M7_BINDING_ENV_PROJECT_REQUIRED');value=values[0]
 if len(value)>1 and value[0]==value[-1] and value[0]in("'",'"'):value=value[1:-1]
 require(NAME.fullmatch(value) is not None,'M7_BINDING_ENV_PROJECT_REQUIRED');return value

def canonical_project(owner,env_file,config_file,expected=None):
 """Never derive namespace from mutable owner alone, and never fall back."""
 project=owner.get('project');config=load(config_file)
 require(isinstance(project,str)and NAME.fullmatch(project)and config.get('name')==project and _environment_project(env_file)==project,'M7_BINDING_PROJECT_MISMATCH')
 if expected is not None:require(project==expected,'M7_BINDING_PROJECT_CHANGED')
 return project

def prefix(project,env_file,config_file):
 require(isinstance(project,str)and NAME.fullmatch(project),'M7_BINDING_PROJECT_REQUIRED')
 return ['docker','compose','-p',project,'--env-file',_absolute(env_file),'-f',_absolute(config_file)]


def _action(args,services):
    values=[str(x)for x in args];i=0
    while i<len(values)and values[i].startswith('-'):
        require(values[i]=='--profile'and i+1<len(values)and values[i+1]=='ops','M7_BINDING_ACTUAL_ARGV_OVERRIDE');i+=2
    require(i<len(values),'M7_BINDING_COMPOSE_ACTION_REQUIRED');action=values[i]
    end=len(values)
    if action in('exec','run'):
        end=next((n for n in range(i+1,len(values))if values[n]in services),len(values))
    forbidden=('-p','--project-name','--env-file','-f','--file','--project-directory')
    require(not any(x in forbidden or x.startswith(('--project-name=','--env-file=','--file='))or x.startswith('-p')and not x.startswith('--')or x.startswith('-f')and not x.startswith('--')for x in values[i+1:end]),'M7_BINDING_ACTUAL_ARGV_OVERRIDE')
    return action

def fixture_argv(directory,args):
 """Cheap check for existing adapter reads; no Docker config per SQL poll."""
 d=Path(directory).resolve();m=load(d/'owner.json');env=d/'env';config=d/'frozen.compose.json'
 require(m.get('environmentSha256')==digest(env)and m.get('composeSha256')==digest(config),'M7_BINDING_FIXTURE_CHANGED')
 if args:_action(args,load(config)['services'])
 return prefix(canonical_project(m,env,config),env,config)+[str(x)for x in args]


def mutation(args):
    # Container lifecycle only. exec/SQL and private inspectors never render config.
    verbs={'up','create','run','start','restart','stop','kill','rm','down','build','pull'}
    values=[str(x)for x in args];i=0
    while i<len(values)and values[i]=='--profile':i+=2
    return i<len(values)and values[i]in verbs

def _memory_representation(config):
    # Compose JSON expands integer byte declarations as decimal strings. Only
    # these two fields may use that exact representation equivalence; retain
    # type tags for every other value so bool/float cannot equal integer bytes.
    value=copy.deepcopy(config)
    for spec in value.get('services',{}).values():
        for key in ('mem_limit','memswap_limit'):
            if key not in spec:continue
            amount=spec[key]
            if type(amount)is int:spec[key]=('bytes',amount)
            elif type(amount)is str and re.fullmatch(r'0|[1-9][0-9]{0,19}',amount):spec[key]=('bytes',int(amount))
            else:spec[key]=('exact-type',type(amount).__name__,amount)
    return value

def fixture_mutation_preflight(directory,argv,runner):
    d=Path(directory).resolve();m=load(d/'owner.json');expected=fixture_argv(d,())
    require(list(argv[:len(expected)])==expected,'M7_BINDING_ACTUAL_ARGV_PROJECT_CONFIG_CHANGED')
    _action(argv[len(expected):],load(d/'frozen.compose.json')['services'])
    value=json.loads(runner(expected+['--profile','ops','config','--format','json']))
    frozen=load(d/'frozen.compose.json')
    same=_memory_representation(value)==_memory_representation(frozen) if 'diagnosticResources'in m else value==frozen
    require(value.get('name')==m['project']and same,'M7_BINDING_EXPANDED_CONFIG_CHANGED')
    return value

def stamp_candidate(config,attempt,roles):
 """Return new declarations only. Never alter an original fixture document."""
 require(re.fullmatch(r'[a-f0-9]{32}',attempt or '')is not None,'M7_BINDING_ATTEMPT_REQUIRED');value=copy.deepcopy(config)
 for role in roles:
  require(role in value['services'],'M7_BINDING_ROLE_UNKNOWN');labels=value['services'][role].setdefault('labels',{});require(isinstance(labels,dict),'M7_BINDING_LABELS_REQUIRED');require(ATTEMPT not in labels,'M7_BINDING_ATTEMPT_ALREADY_DECLARED');labels[ATTEMPT]=attempt
 return value

def _tmpfs(spec):
 result={}
 for value in spec.get('tmpfs',[]):
  require(isinstance(value,str),'M7_BINDING_TMPFS_INVALID');key,_,opts=value.partition(':');result[key]=opts
 return result

def _layout(config,role,image_id,app_roles,pair,state_root,config_files,image_config=None):
 spec=config['services'][role];require(IMAGE.fullmatch(image_id or '')is not None,'M7_BINDING_IMAGE_ID_REQUIRED');mounts=[]
 for value in spec.get('volumes',[]):
  kind=value.get('type');require(kind in('bind','volume'),'M7_BINDING_MOUNT_KIND')
  source=_absolute(value['source'])if kind=='bind'else config.get('volumes',{}).get(value['source'],{}).get('name',value['source'])
  if kind=='bind':require(Path(source).is_relative_to(Path(state_root)),'M7_BINDING_FOREIGN_STATE_MOUNT')
  mounts.append([kind,source,value['target'],not value.get('read_only',False)])
 environment=spec.get('environment',{});require(isinstance(environment,dict),'M7_BINDING_ENVIRONMENT_INVALID')
 if image_config is not None:require(image_config.get('Id')==image_id and isinstance(image_config.get('Config'),dict),'M7_BINDING_IMAGE_METADATA_CHANGED')
 if spec.get('command')is not None:command=spec['command']
 else:
  require(image_config is not None and 'Cmd'in image_config['Config'],'M7_BINDING_IMAGE_COMMAND_REQUIRED');command=image_config['Config']['Cmd']
 entrypoint=spec['entrypoint']if spec.get('entrypoint')is not None else image_config['Config'].get('Entrypoint')if image_config else None
 if role in app_roles:
  for values in (environment,spec.get('build',{}).get('args',{})if isinstance(spec.get('build'),dict)else{}):
   for key,field in [('NS_SOURCE_COMMIT','core'),('NS_DEPLOY_COMMIT','deploy')]:
    if key in values:require(values[key]==pair[field],'M7_BINDING_SOURCE_DECLARATION_CHANGED')
 return {'imageId':image_id,'configuredImage':spec['image'],'command':command,'entrypoint':entrypoint,'mounts':sorted(mounts),'tmpfs':_tmpfs(spec),'environmentHashes':{k:sha(str(v).encode())for k,v in environment.items()},'appSource':pair if role in app_roles else None,'configFiles':[_absolute(x)for x in config_files],'attempt':spec.get('labels',{}).get(ATTEMPT),'networks':sorted(config.get('networks',{}).get(k,{}).get('name',k)for k in spec.get('networks',{}))}


def image_metadata(config,runner):
    """Resolve only pinned local image metadata; never pull/build or infer a row."""
    images={};configs={};cache={}
    for role,spec in config['services'].items():
        ref=spec['image']
        if ref not in cache:
            value=json.loads(runner(['docker','image','inspect',ref]));require(len(value)==1 and IMAGE.fullmatch(value[0].get('Id','')),'M7_BINDING_IMAGE_METADATA_CHANGED');cache[ref]=value[0]
        metadata=cache[ref];images[role]=metadata['Id'];configs[role]={'Id':metadata['Id'],'Config':{k:metadata['Config'].get(k)for k in('Cmd','Entrypoint')}}
    return {'imageIds':images,'imageConfigs':configs}

def make_binding(owner_file,env_file,epochs,target_epoch,state_root,attempt,run_stages=None,oneoff_root=None,oneoff_images=None):
 """Freeze authored epoch documents after source/image preparation, before GO.

    epochs[name]={configFile,imageIds,appRoles,pair,configFiles?}. configFiles
    can preserve a historical original container's recorded Compose file list.
    """
 owner_file=_absolute(owner_file);env_file=_absolute(env_file);owner=load(owner_file);state_root=_absolute(state_root)
 require(re.fullmatch(r'[a-f0-9]{32}',owner.get('owner',''))and re.fullmatch(r'[a-f0-9]{32}',attempt or ''),'M7_BINDING_OWNER_ATTEMPT_REQUIRED')
 require(target_epoch in epochs,'M7_BINDING_TARGET_EPOCH_REQUIRED');frozen={};project=None
 for name,value in epochs.items():
  file=_absolute(value['configFile']);config=load(file);selected=canonical_project(owner,env_file,file,project);project=selected;pair=value['pair'];require(set(pair)=={'core','deploy'}and all(re.fullmatch('[a-f0-9]{40}',x or '')for x in pair.values()),'M7_BINDING_SOURCE_PAIR_REQUIRED')
  layouts={}
  for role,spec in config['services'].items():
   require(spec.get('labels',{}).get(OWNER)==owner['owner'],'M7_BINDING_DECLARED_OWNER_CHANGED')
   files=value.get('configFiles',{}).get(role,[file]);layouts[role]=_layout(config,role,value['imageIds'].get(role),value['appRoles'],pair,state_root,files,value.get('imageConfigs',{}).get(role))
  frozen[name]={'configFile':file,'sha256':digest(file),'config':config,'layouts':layouts}
 target=frozen[target_epoch];require(any(x['attempt']==attempt for x in target['layouts'].values()),'M7_BINDING_NEW_ATTEMPT_LABEL_REQUIRED')
 result={'version':1,'project':project,'owner':owner['owner'],'ownerFile':owner_file,'ownerSha256':digest(owner_file),'envFile':env_file,'envSha256':digest(env_file),'stateRoot':state_root,'attempt':attempt,'targetEpoch':target_epoch,'epochs':frozen}
 result['runStages']={}
 if oneoff_root is not None:
  result['oneoffRoot']=_absolute(oneoff_root);result['oneoffImages']=dict(oneoff_images or{});require(set(result['oneoffImages'])=={'k6'}and all(IMAGE.fullmatch(x)for x in result['oneoffImages'].values()),'M7_BINDING_ONEOFF_IMAGE_REQUIRED')
 for name,stage in (run_stages or{}).items():
  require(NAME.fullmatch(name)and set(stage)=={'epoch','argv','sourceFile'},'M7_BINDING_RUN_STAGE_INVALID');epoch=stage['epoch'];require(epoch in frozen,'M7_BINDING_EPOCH_UNKNOWN');args=list(stage['argv']);source=_absolute(stage['sourceFile']);require(args[:3]==['--profile','ops','run'],'M7_BINDING_RUN_STAGE_PROFILE_REQUIRED');args=args[3:];index=next((i for i,x in enumerate(args)if x in frozen[epoch]['layouts']),-1);require(index>=0,'M7_BINDING_ROLE_UNKNOWN');options=args[:index];role=args[index];command=args[index+1:];_options('run',options);require(all(isinstance(x,str)and 0<len(x)<=4096 for x in command)and not any(x in('-p','--project-name','--env-file','-f','--file','--project-directory')or x.startswith(('--project-name=','--env-file=','--file='))for x in command),'M7_BINDING_RUN_STAGE_COMMAND_REQUIRED');_action(['run',*options,role,*command],frozen[epoch]['layouts']);layout=copy.deepcopy(frozen[epoch]['layouts'][role]);layout['command']=command or layout['command'];layout['attempt']=attempt;result['runStages'][name]={'epoch':epoch,'role':role,'options':options,'command':command,'sourceFile':source,'sourceSha256':digest(source),'layout':layout}
 result['sha256']=sha(encode(result));return result

def verify(binding):
 require(binding.get('version')==1 and binding.get('sha256')==sha(encode({k:v for k,v in binding.items()if k!='sha256'})),'M7_BINDING_SEAL_CHANGED')
 require(digest(binding['ownerFile'])==binding['ownerSha256']and digest(binding['envFile'])==binding['envSha256'],'M7_BINDING_OWNER_ENV_CHANGED')
 for epoch in binding['epochs'].values():
  require(digest(epoch['configFile'])==epoch['sha256'],'M7_BINDING_COMPOSE_CHANGED');canonical_project(load(binding['ownerFile']),binding['envFile'],epoch['configFile'],binding['project'])
 # Source bytes describe the producer; the actual image, command and owned
 # Compose layout below protect effects. Editing a producer cannot alter them.
 return binding

def _options(action,options):
 allowed={'up':{'-d','--no-deps','--no-build','--force-recreate','--wait','--pull','never','--wait-timeout'},'create':{'--no-build','--no-deps','--pull','never'},'run':{'--rm','--no-deps','--pull','never'}}
 options=[str(x)for x in options];i=0
 while i<len(options):
  value=options[i]
  if action=='run' and value.startswith('--env=NS_DEMO_TENANTS='):
   count=value.removeprefix('--env=NS_DEMO_TENANTS=')
   require(re.fullmatch('[1-9][0-9]{0,15}',count) and workload_inputs.tenants(int(count)),
           'M7_BINDING_COMPOSE_OPTION_REFUSED')
   i+=1;continue
  require(value in allowed[action]and value!='never','M7_BINDING_COMPOSE_OPTION_REFUSED')
  if value in('--pull','--wait-timeout'):
   require(i+1<len(options),'M7_BINDING_COMPOSE_OPTION_REFUSED');argument=options[i+1];require(argument=='never'if value=='--pull'else re.fullmatch(r'[0-9]{1,10}',argument)and workload_inputs.seconds(int(argument)),'M7_BINDING_COMPOSE_OPTION_REFUSED');i+=2
  else:i+=1
 return options

def compose_argv(binding,action,roles,options=(),epoch=None,stage=None):
 """The only mutating Compose prefix/namespace constructor."""
 verify(binding);epoch=epoch or binding['targetEpoch'];require(epoch in binding['epochs'],'M7_BINDING_EPOCH_UNKNOWN');roles=list(roles);require(roles and len(set(roles))==len(roles)and all(r in binding['epochs'][epoch]['layouts']for r in roles),'M7_BINDING_ROLE_UNKNOWN')
 require(action in('up','create','run'),'M7_BINDING_USE_RECORDED_IDS');options=_options(action,options);command=[]
 if stage is not None:
  require(stage in binding.get('runStages',{}),'M7_BINDING_RUN_STAGE_UNKNOWN');declared=binding['runStages'][stage];require(action=='run'and epoch==declared['epoch']and roles==[declared['role']]and options==declared['options'],'M7_BINDING_RUN_STAGE_CHANGED');command=declared['command']
 if action=='run':require(len(roles)==1,'M7_BINDING_RUN_ONE_SERVICE');options+=['--label',ATTEMPT+'='+binding['attempt']]
 else:require(all(binding['epochs'][epoch]['layouts'][r]['attempt']==binding['attempt']for r in roles),'M7_BINDING_NEW_ATTEMPT_LABEL_REQUIRED')
 return prefix(binding['project'],binding['envFile'],binding['epochs'][epoch]['configFile'])+['--profile','ops',action,*options,*roles,*command]

def check_expanded(binding,argv,runner,epoch=None):
 verify(binding);epoch=epoch or binding['targetEpoch'];expected=prefix(binding['project'],binding['envFile'],binding['epochs'][epoch]['configFile']);require(list(argv[:len(expected)])==expected,'M7_BINDING_ACTUAL_ARGV_PROJECT_CONFIG_CHANGED')
 # Global options supplied after the action may also override Compose's prefix.
 require(not any(x in('-p','--project-name','--env-file','-f','--file','--project-directory')or x.startswith(('--project-name=','--env-file=','--file='))for x in argv[len(expected):]),'M7_BINDING_ACTUAL_ARGV_OVERRIDE')
 _action(argv[len(expected):],binding['epochs'][epoch]['layouts'])
 actual=json.loads(runner(expected+['--profile','ops','config','--format','json']));require(actual.get('name')==binding['project'],'M7_BINDING_EXPANDED_PROJECT_CHANGED')
 frozen=binding['epochs'][epoch]['config']
 same=_memory_representation(actual)==_memory_representation(frozen) if 'diagnosticResources'in load(binding['ownerFile']) else actual==frozen
 require(same,'M7_BINDING_EXPANDED_CONFIG_CHANGED');return actual

def _actual_layout(row):
 cfg=row['Config'];mounts=[]
 for v in row.get('Mounts',[]):
  kind=v['Type']
  if kind in('bind','volume'):mounts.append([kind,_absolute(v['Source'])if kind=='bind'else v['Name'],v['Destination'],v['RW']])
  else:require(kind=='tmpfs'and v['Destination']in(row.get('HostConfig',{}).get('Tmpfs')or{}),'M7_BINDING_RUNTIME_MOUNT_KIND')
 return cfg,mounts

def qualify_row(binding,row,epoch,created=False,stage=None):
 require(HEX.fullmatch(row.get('Id',''))is not None,'M7_BINDING_FULL_INSPECT_ID_REQUIRED');cfg,mounts=_actual_layout(row);labels=cfg.get('Labels')or{};role=labels.get(SERVICE);require(labels.get(PROJECT)==binding['project']and labels.get(OWNER)==binding['owner'],'M7_BINDING_FOREIGN_OWNER_PROJECT');layout=binding['runStages'][stage]['layout']if stage else binding['epochs'][epoch]['layouts'].get(role);require(layout is not None and (not stage or binding['runStages'][stage]['epoch']==epoch and binding['runStages'][stage]['role']==role),'M7_BINDING_ROLE_UNKNOWN')
 require(row['Image']==layout['imageId']and cfg.get('Image')==layout['configuredImage'],'M7_BINDING_RUNTIME_IMAGE_CHANGED');require(cfg.get('Cmd')==layout['command'],'M7_BINDING_ROLE_COMMAND_CHANGED')
 if layout['entrypoint']is not None:require(cfg.get('Entrypoint')==layout['entrypoint'],'M7_BINDING_ROLE_ENTRYPOINT_CHANGED')
 require(sorted(mounts)==layout['mounts']and(row.get('HostConfig',{}).get('Tmpfs')or{})==layout['tmpfs'],'M7_BINDING_ROLE_MOUNTS_CHANGED')
 env=dict(x.split('=',1)for x in cfg.get('Env',[])if'='in x);require(all(k in env and sha(env[k].encode())==v for k,v in layout['environmentHashes'].items()),'M7_BINDING_ROLE_ENV_CHANGED');files=[_absolute(x)for x in labels.get(CONFIG_FILES,'').split(',')if x];require(files==layout['configFiles'],'M7_BINDING_RUNTIME_CONFIG_FILES_CHANGED')
 if layout['appSource']:
  require(labels.get('org.opencontainers.image.revision')==layout['appSource']['core']and labels.get('org.nightscout.deploy.revision')==layout['appSource']['deploy'],'M7_BINDING_RUNTIME_SOURCE_CHANGED')
 if layout['networks']:require(sorted(row.get('NetworkSettings',{}).get('Networks',{}))==layout['networks'],'M7_BINDING_RUNTIME_NETWORK_CHANGED')
 if layout['attempt']is not None:require(labels.get(ATTEMPT)==layout['attempt'],'M7_BINDING_CREATED_ATTEMPT_CHANGED')
 if created:require(labels.get(ATTEMPT)==binding['attempt'],'M7_BINDING_CREATED_ATTEMPT_CHANGED')
 return {**({'stage':stage}if stage else{}),'id':row['Id'],'epoch':epoch,'service':role,'created':row.get('Created'),'imageId':row['Image'],'layoutSha256':sha(encode(layout)),'environmentSha256':sha(encode(sorted(cfg.get('Env',[]))))}

def _save(path,value,exclusive=False):
 path=Path(path);tmp=path.with_name(path.name+'.partial-'+str(os.getpid()));tmp.parent.mkdir(parents=True,exist_ok=True)
 try:
  with tmp.open('x')as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
  tmp.chmod(0o600)
  if exclusive:os.link(tmp,path)
  else:os.replace(tmp,path)
 finally:
  try:tmp.unlink()
  except FileNotFoundError:pass

def begin_journal(binding,rows,path,original_epoch='original'):
 verify(binding);require(not Path(path).exists(),'M7_BINDING_JOURNAL_EXISTS');entries={}
 for row in rows:
  record=qualify_row(binding,row,original_epoch);require(record['id']not in entries,'M7_BINDING_DUPLICATE_ID');entries[record['id']]=record
 journal={'version':1,'bindingSha256':binding['sha256'],'binding':copy.deepcopy(binding),'records':entries,'intents':[]};_save(path,journal,exclusive=True);return journal

def _inspect(runner,ids,allow_absent=False):
 if allow_absent and len(ids)==1:
  present=runner(['docker','ps','-aq','--no-trunc','--filter','id='+ids[0]]).split()
  if not present:return []
  require(present==ids,'M7_BINDING_FULL_INSPECT_ID_REQUIRED')
 return json.loads(runner(['docker','inspect',*ids]))if ids else[]
def _created_seconds(value):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def record_created(journal,runner):
 binding=journal['binding'];ids=runner(['docker','ps','-aq','--no-trunc','--filter','label='+ATTEMPT+'='+binding['attempt']]).split();rows=_inspect(runner,ids);refused=[]
 for row in rows:
  if row['Id']in journal['records']:continue
  matches=[]
  for intent in journal['intents']:
   if intent.get('resource')=='oneoff':
    try:record=qualify_oneoff(binding,row,intent);require(_created_seconds(row['Created'])>=intent['notBefore'],'M7_BINDING_CREATED_TIME_CHANGED');matches.append(record)
    except (RuntimeError,ValueError,TypeError,KeyError):pass
    continue
   if row['Config'].get('Labels',{}).get(SERVICE)not in intent['roles']:continue
   try:record=qualify_row(binding,row,intent['epoch'],created=True,stage=intent.get('stage'));require(_created_seconds(row['Created'])>=intent['notBefore'],'M7_BINDING_CREATED_TIME_CHANGED');matches.append(record)
   except (RuntimeError,ValueError,TypeError,KeyError):continue
  if not matches or not all(x==matches[0]for x in matches):refused.append(row.get('Id'));continue
  journal['records'][row['Id']]=matches[0]
 require(not refused,'M7_BINDING_UNOWNED_CREATED_ID')
 return journal

def checked_run(binding,action,roles,runner,authorize,journal_file,options=(),epoch=None,actual_argv=None,stage=None):
 """Use the existing finite authorizer; capture failure never weakens custody."""
 require(callable(authorize),'M7_BINDING_FINITE_AUTHORIZER_REQUIRED');epoch=epoch or binding['targetEpoch'];argv=compose_argv(binding,action,roles,options,epoch,stage);require(actual_argv is None or list(actual_argv)==argv,'M7_BINDING_ACTUAL_ARGV_CHANGED');check_expanded(binding,argv,runner,epoch);journal=load(journal_file);require(journal['bindingSha256']==binding['sha256'],'M7_BINDING_JOURNAL_CHANGED');journal['intents'].append({'epoch':epoch,'roles':list(roles),'action':action,**({'stage':stage}if stage else{}),'notBefore':time.time(),'argvSha256':sha(encode(argv))});_save(journal_file,journal);require(authorize()is not False,'M7_BINDING_FINITE_AUTHORIZER_REFUSED')
 try:return runner(argv)
 finally:
  record_created(journal,runner);_save(journal_file,journal)


def checked_ids(journal_file,action,ids,runner,authorize):
    """Existing exact-container start/restart/stop, under the same declaration proof."""
    require(action in('start','restart','stop')and callable(authorize),'M7_BINDING_ID_ACTION_REFUSED')
    journal=load(journal_file);binding=journal['binding'];verify(binding);ids=list(ids)
    require(ids and len(set(ids))==len(ids)and all(cid in journal['records']for cid in ids),'M7_BINDING_UNRECORDED_ID')
    epochs={}
    for cid in ids:
        record=journal['records'][cid];rows=_inspect(runner,[cid],allow_absent=True);require(len(rows)==1,'M7_BINDING_RECORDED_ID_MISSING');require(qualify_record(binding,rows[0],record)==record,'M7_BINDING_RECORDED_EPOCH_CHANGED');
        if record.get('resource')=='oneoff':require(action=='stop','M7_BINDING_ONEOFF_RESTART_REFUSED')
        else:epochs.setdefault(record['epoch'],[]).append(record['service'])
    for epoch,roles in epochs.items():
        argv=prefix(binding['project'],binding['envFile'],binding['epochs'][epoch]['configFile'])+[action,*roles];check_expanded(binding,argv,runner,epoch)
    require(authorize()is not False,'M7_BINDING_FINITE_AUTHORIZER_REFUSED');argv=['docker',action,*(['--time','30']if action=='stop'else[]),*ids];return runner(argv)

def cleanup_recorded(journal_file,runner,authorize):
 """No mutable project/env/config lookup. Stop only proven recorded/attempt IDs."""
 require(callable(authorize),'M7_BINDING_FINITE_AUTHORIZER_REQUIRED');journal=load(journal_file);binding=journal['binding'];require(binding.get('sha256')==journal['bindingSha256']and binding['sha256']==sha(encode({k:v for k,v in binding.items()if k!='sha256'})),'M7_BINDING_JOURNAL_CHANGED');refused=[]
 try:record_created(journal,runner)
 except Exception as error:refused.append(str(error)if re.fullmatch(r'M7_[A-Z_]+',str(error))else'M7_BINDING_DISCOVERY_UNAVAILABLE')
 # Unknown project members are evidence of a custody mismatch, never kill targets.
 try:
  ids=runner(['docker','ps','-aq','--no-trunc','--filter','label='+PROJECT+'='+binding['project']]).split()
  if any(cid not in journal['records']for cid in ids):refused.append('M7_BINDING_UNRECORDED_PROJECT_ID')
 except Exception:refused.append('M7_BINDING_PROJECT_INVENTORY_UNAVAILABLE')
 persisted=True
 try:_save(journal_file,journal)
 except OSError:persisted=False
 safe=[];absent=[]
 for cid,record in journal['records'].items():
  try:rows=_inspect(runner,[cid],allow_absent=True)
  except Exception:refused.append('M7_BINDING_INSPECT_UNAVAILABLE');continue
  if not rows:absent.append(cid);continue
  try:
   require(len(rows)==1 and rows[0]['Id']==cid,'M7_BINDING_RECORDED_ID_CHANGED');observed=qualify_record(binding,rows[0],record);require(observed==record,'M7_BINDING_RECORDED_EPOCH_CHANGED')
  except RuntimeError as error:refused.append(str(error));continue
  if rows[0]['State']['Running']:safe.append(cid)
 require(authorize()is not False,'M7_BINDING_FINITE_AUTHORIZER_REFUSED')
 if safe:runner(['docker','stop','--time','30',*safe])
 remaining=[]
 for cid in safe:
  rows=_inspect(runner,[cid],allow_absent=True);remaining.extend(x['Id']for x in rows if x['State']['Running'])
 require(not remaining,'M7_BINDING_OWNED_RUNNING_REMAIN');return {'status':'OWNED_STOPPED_FOREIGN_REFUSED'if refused else'EXACT_RECORDED_IDS_STOPPED','stoppedIds':safe,'absentIds':absent,'refusals':refused,'journalPersisted':persisted,'volumes':'PRESERVED','mutableDeclarationRead':False}


def qualify_record(binding,row,record):
 if record.get('resource')=='oneoff':return qualify_oneoff(binding,row,record['intent'])
 return qualify_row(binding,row,record['epoch'],stage=record.get('stage'))

def _oneoff_intent(binding,kind,argv,scope,runner,cidfile):
 """Only three existing source-generated k6 commands, with exact declared layout."""
 require(kind in('k6-version','k6-help','k6-load'),'M7_BINDING_ONEOFF_KIND_REFUSED');require(set(scope)=={'directory','owner','imageId'},'M7_BINDING_ONEOFF_SCOPE_REQUIRED');directory=_absolute(scope['directory']);owner=load(Path(directory)/'owner.json');require(owner.get('attached')is True and owner.get('owner')==scope['owner']and owner.get('project')==binding['project'],'M7_BINDING_ONEOFF_ATTACHMENT_CHANGED');require(Path(directory).is_relative_to(Path(binding['oneoffRoot']))and re.fullmatch('[a-f0-9]{32}',scope['owner']or'')and scope['imageId']==binding['oneoffImages']['k6'],'M7_BINDING_ONEOFF_SCOPE_CHANGED')
 argv=list(map(str,argv));require(argv[:3]==['docker','run','--rm'],'M7_BINDING_ONEOFF_ARGV_REFUSED');i=3;labels={};env={};mounts=[];network=None;user=None;name=None;resource_limits=None;pull_policy=None
 if 'diagnosticResources'in owner:
  import diagnostic_resources as resource
  config=load(Path(directory)/'frozen.compose.json');budget=resource.plan(config);resource.verify_config(config,budget);require(owner['diagnosticResources']==budget.record(),'M7_BINDING_ONEOFF_RESOURCE_RECORD_CHANGED')
  allocation_file=Path(directory)/'loadgen-resource-allocation.json'
  if allocation_file.is_file():
   allocation=load(allocation_file);require(allocation==resource.discovery_driver_record(owner)and allocation is not None,'M7_BINDING_ONEOFF_DRIVER_ALLOCATION_CHANGED');limit=resource.DISCOVERY_K6
  else:limit=resource.LIMITS['k6']
  require(argv[3:9]==['--cpus',limit.cpus,'--memory',str(limit.memory),'--memory-swap',str(limit.memory)],'M7_BINDING_ONEOFF_RESOURCE_LIMITS_CHANGED');i=9
  resource_limits={'NanoCpus':limit.cpu*1000000,'Memory':limit.memory,'MemorySwap':limit.memory}
 while i<len(argv)and argv[i]!=scope['imageId']:
  key=argv[i];require(key in('--label','--network','--name','-u','-v','-e','--pull')and i+1<len(argv),'M7_BINDING_ONEOFF_OPTION_REFUSED');value=argv[i+1];i+=2
  if key=='--label':
   k,v=value.split('=',1);require(k not in labels,'M7_BINDING_ONEOFF_LABEL_REFUSED');labels[k]=v
  elif key=='-e':
   k,v=value.split('=',1);require(k not in env,'M7_BINDING_ONEOFF_ENV_REFUSED');env[k]=v
  elif key=='-v':
   parts=value.split(':');require(len(parts)in(2,3)and(len(parts)==2 or parts[2]=='ro'),'M7_BINDING_ONEOFF_MOUNT_REFUSED');source=_absolute(parts[0]);require(Path(source).is_relative_to(Path(directory)),'M7_BINDING_ONEOFF_MOUNT_REFUSED');mounts.append(['bind',source,parts[1],len(parts)==2])
  elif key=='--pull':require(resource_limits is not None and pull_policy is None and value=='never','M7_BINDING_ONEOFF_PULL_POLICY_CHANGED');pull_policy=value
  elif key=='--network':require(network is None,'M7_BINDING_ONEOFF_OPTION_REFUSED');network=value
  elif key=='-u':require(user is None,'M7_BINDING_ONEOFF_OPTION_REFUSED');user=value
  else:require(name is None,'M7_BINDING_ONEOFF_OPTION_REFUSED');name=value
 if resource_limits is not None:require(pull_policy=='never','M7_BINDING_ONEOFF_PULL_POLICY_CHANGED')
 require(i<len(argv),'M7_BINDING_ONEOFF_IMAGE_CHANGED');command=argv[i+1:];require(labels.get(OWNER)==scope['owner']and labels.get(PROJECT)==binding['project'],'M7_BINDING_ONEOFF_OWNER_PROJECT_CHANGED');require(set(labels)==({OWNER,PROJECT,SERVICE}if kind=='k6-load'else{OWNER,PROJECT}),'M7_BINDING_ONEOFF_LABEL_REFUSED')
 if kind=='k6-load':
  require(labels[SERVICE]=='k6'and network=='host'and name==binding['project']+'-k6'and re.fullmatch('[0-9]+:[0-9]+',user or'')and sorted(mounts)==sorted([['bind',directory+'/k6','/scripts',False],['bind',directory+'/load','/out',True],['bind',directory+'/tenants.private.json','/tenants.private.json',False]]),'M7_BINDING_ONEOFF_LOAD_LAYOUT_CHANGED')
  require(command==['run','--quiet','--summary-export','/out/k6-summary.json','/scripts/workload.js']and set(env)=={'BASE_URL','TENANTS_FILE','RUN_ID','RUN_START','DURATION','ACCEL','HOT_FACTOR','SHAPES'}|({'OFFERED_RPS'}if'OFFERED_RPS'in env else set())|({'JWT_SETUP_CONCURRENCY'}if'JWT_SETUP_CONCURRENCY'in env else set())|({'M7_SETUP_SECONDS','M7_SETUP_UNTIL_MS'}if'M7_SETUP_SECONDS'in env or'M7_SETUP_UNTIL_MS'in env else set()),'M7_BINDING_ONEOFF_LOAD_COMMAND_CHANGED')
  if 'M7_SETUP_SECONDS'in env or 'setupSeconds'in owner.get('cadence',{}):
   import phase_windows
   selected=phase_windows.selection(owner.get('cadence',{}));window=load(Path(directory)/'load/phase-windows.json')
   require('setupSeconds'in selected and re.fullmatch('[1-9][0-9]*',env.get('M7_SETUP_SECONDS',''))is not None and 1<=int(env['M7_SETUP_SECONDS'])<=selected['setupSeconds']and window.get('owner')==scope['owner']and window.get('setupSeconds')==selected['setupSeconds']and env.get('M7_SETUP_UNTIL_MS')==str(window.get('setupUntilUnixMs')),'M7_BINDING_ONEOFF_SETUP_WINDOW_CHANGED')
  if 'JWT_SETUP_CONCURRENCY'in env or 'jwtSetupConcurrency'in owner:
   concurrency=owner.get('jwtSetupConcurrency',1);require(workload_inputs.concurrency(concurrency) and (owner.get('runPurpose')=='discovery' or concurrency<=64) and env.get('JWT_SETUP_CONCURRENCY')==str(concurrency),'M7_BINDING_ONEOFF_JWT_SETUP_CHANGED')
 else:require(command==(['version']if kind=='k6-version'else['run','--help'])and network=='none'and not mounts and not env and user is None and name is None,'M7_BINDING_ONEOFF_PROBE_COMMAND_CHANGED')
 meta=json.loads(runner(['docker','image','inspect',scope['imageId']]))[0];require(meta['Id']==scope['imageId'],'M7_BINDING_ONEOFF_IMAGE_CHANGED');default=meta['Config'];merged=dict(x.split('=',1)for x in default.get('Env',[])if'='in x);merged.update(env)
 layout={'imageId':scope['imageId'],'command':command,'entrypoint':default.get('Entrypoint'),'environmentHashes':{k:sha(v.encode())for k,v in merged.items()},'mounts':sorted(mounts),'network':network,'user':user or default.get('User',''),'owner':scope['owner'],'labels':{**labels,ATTEMPT:binding['attempt']}}
 if resource_limits is not None:layout['resourceLimits']=resource_limits
 return {'resource':'oneoff','kind':kind,'notBefore':time.time(),'cidFile':str(cidfile),'attachmentSha256':digest(Path(directory)/'owner.json'),'layout':layout,'argvSha256':sha(encode(argv))}

def qualify_oneoff(binding,row,intent):
 require(HEX.fullmatch(row.get('Id',''))is not None,'M7_BINDING_FULL_INSPECT_ID_REQUIRED');cidfile=Path(intent['cidFile']);require(not cidfile.exists()or cidfile.read_text().strip()==row['Id'],'M7_BINDING_ONEOFF_CIDFILE_CHANGED');layout=intent['layout'];cfg,mounts=_actual_layout(row);labels=cfg.get('Labels')or{};require(all(labels.get(k)==v for k,v in layout['labels'].items())and labels.get(CONFIG_FILES)in(None,''),'M7_BINDING_ONEOFF_LABEL_CHANGED');require(row['Image']==layout['imageId']and cfg.get('Image')==layout['imageId']and cfg.get('Cmd')==layout['command']and cfg.get('Entrypoint')==layout['entrypoint'],'M7_BINDING_ONEOFF_COMMAND_IMAGE_CHANGED');require(sorted(mounts)==layout['mounts']and not(row.get('HostConfig',{}).get('Tmpfs')or{})and row['HostConfig'].get('NetworkMode')==layout['network']and cfg.get('User','')==layout['user']and not row['HostConfig'].get('Privileged'),'M7_BINDING_ONEOFF_LAYOUT_CHANGED');env=dict(x.split('=',1)for x in cfg.get('Env',[])if'='in x);require({k:sha(v.encode())for k,v in env.items()}==layout['environmentHashes'],'M7_BINDING_ONEOFF_ENV_CHANGED')
 if 'resourceLimits'in layout:require({k:row.get('HostConfig',{}).get(k)for k in layout['resourceLimits']}==layout['resourceLimits'],'M7_BINDING_ONEOFF_RESOURCE_LIMITS_CHANGED')
 return {'resource':'oneoff','intent':intent,'id':row['Id'],'epoch':None,'service':intent['kind'],'created':row.get('Created'),'imageId':row['Image'],'layoutSha256':sha(encode(layout)),'environmentSha256':sha(encode(sorted(cfg.get('Env',[]))))}

def checked_oneoff(binding,kind,argv,scope,runner,authorize,journal_file):
 """Prewrite exact source-generated k6 intent before the existing CLI runner."""
 verify(binding);require(callable(authorize),'M7_BINDING_FINITE_AUTHORIZER_REQUIRED');journal=load(journal_file);require(journal['bindingSha256']==binding['sha256'],'M7_BINDING_JOURNAL_CHANGED');folder=Path(binding['oneoffRoot'])/'oneoff-cids';folder.mkdir(mode=0o700,exist_ok=True);cidfile=folder/(str(len(journal['intents']))+'.cid');require(not cidfile.exists(),'M7_BINDING_ONEOFF_CIDFILE_EXISTS');intent=_oneoff_intent(binding,kind,argv,scope,runner,cidfile);journal['intents'].append(intent);_save(journal_file,journal);require(authorize()is not False,'M7_BINDING_FINITE_AUTHORIZER_REFUSED');actual=list(map(str,argv));offset=9 if 'resourceLimits'in intent['layout']else 3;actual[offset:offset]=['--label',ATTEMPT+'='+binding['attempt'],'--cidfile',str(cidfile)]
 try:return runner(actual)
 finally:
  record_created(journal,runner);_save(journal_file,journal)
