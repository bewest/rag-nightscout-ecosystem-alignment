"""Remote adoption of the shared immutable Compose/custody core; no actors on import."""
import copy,hashlib,json,time,uuid
from pathlib import Path
from protocol import binding,need,write
import producer
# producer installs the source-owned m7 module path.
a=producer.a
core=a.orchestration_binding

BINDING='orchestration-binding.json'
JOURNAL='orchestration-journal.json'

def preflight(directory):
 d=Path(directory).resolve();core.fixture_argv(d,());return d,a.document(d/'owner.json')

def authorize(directory,cleanup=False):
 d=Path(directory).resolve();snapshot=d/'orchestration-owner.json';live={}if cleanup else a.document(d/'owner.json');m=a.document(snapshot)if snapshot.exists()else live
 if not cleanup and snapshot.exists():
  need(all(live.get(k)==m.get(k)for k in('owner','project','pair','imageId','tenants','replicas','cadence','port','preparedExternalBinding','externalBinding','environmentSha256','composeSha256','remoteOverlaySha256')),'REMOTE_LIVE_BINDING_CHANGED')
 raw=m.get('externalBinding')or m.get('preparedExternalBinding')
 need(isinstance(raw,dict),'REMOTE_FINITE_BINDING_REQUIRED')
 binding(raw,raw['expiresAt']-541 if cleanup else None)
 return True

def freeze(directory):
 d,m=preflight(directory);need(not(d/BINDING).exists()and not(d/JOURNAL).exists(),'REMOTE_BINDING_ALREADY_FROZEN')
 need(not a.resources(m),'REMOTE_BINDING_BEFORE_RESOURCE_ONLY');authorize(d)
 config=a.document(d/'frozen.compose.json');attempt=uuid.uuid4().hex
 from transport import verify_overlay
 raw=m.get('externalBinding');need(isinstance(raw,dict),'REMOTE_INGRESS_BEFORE_FREEZE_REQUIRED')
 evidence=a.document(d/'remote-overlay.json');verify_overlay(config,raw,evidence)
 stamped=core.stamp_candidate(config,attempt,list(config['services']))
 original=copy.deepcopy(stamped);original['services']['nginx']['ports'].pop()
 digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 rebased={**evidence,'beforeSha256':digest(original),'afterSha256':digest(stamped),'freezeTransform':{'kind':'attempt-labels-v1','attempt':attempt,'previousEvidenceSha256':a.digest(d/'remote-overlay.json'),'previousBeforeSha256':evidence['beforeSha256'],'previousAfterSha256':evidence['afterSha256']}}
 verify_overlay(stamped,raw,rebased)
 previous=d/'remote-overlay.before-freeze.json'
 with previous.open('xb')as saved:saved.write((d/'remote-overlay.json').read_bytes())
 previous.chmod(0o600)
 # Individual files replace atomically; owner hash is committed last. Any interrupted update fails closed.
 write(d/'remote-overlay.json',rebased);write(d/'frozen.compose.json',stamped);m['remoteOverlaySha256']=a.digest(d/'remote-overlay.json');m['composeSha256']=a.digest(d/'frozen.compose.json');m['orchestrationHome']=str(d);write(d/'owner.json',m)
 write(d/'orchestration-owner.json',m)
 metadata=core.image_metadata(stamped,a.command)
 spec={**metadata,'configFile':str(d/'frozen.compose.json'),'appRoles':[role for role,value in stamped['services'].items()if value['image']==m['imageId']],'pair':m['pair']}
 stages={name:{'epoch':'candidate','argv':args,'sourceFile':str(Path(producer.__file__).resolve())}for name,scope,args in producer.deployment_plan(stamped,True,m.get('primerConcurrency',1),static_manifest=m if m.get('staticTopology') else None,platform_verification=bool(m.get('platformStartup')))if scope=='compose'and'run'in args}
 frozen=core.make_binding(d/'orchestration-owner.json',d/'env',{'candidate':spec},'candidate',d/'state',attempt,run_stages=stages)
 write(d/BINDING,frozen);core.begin_journal(frozen,[],d/JOURNAL,original_epoch='candidate');return frozen

def existing(directory):
 d,m=preflight(directory);home=Path(m.get('orchestrationHome','')).resolve()
 need(home==d,'REMOTE_CANONICAL_BINDING_HOME_REQUIRED');frozen=a.document(home/BINDING);core.verify(frozen)
 need(m.get('remoteOverlaySha256')==a.digest(d/'remote-overlay.json')==a.document(d/'orchestration-owner.json').get('remoteOverlaySha256'),'REMOTE_FROZEN_OVERLAY_CHANGED')
 need(frozen['project']==m['project']and frozen['owner']==m['owner']and frozen['epochs']['candidate']['sha256']==m['composeSha256'],'REMOTE_LIVE_BINDING_CHANGED')
 return d,m,frozen

def cleanup(directory):
 d=Path(directory).resolve()
 if not(d/JOURNAL).exists():
  m=a.document(d/'owner.json')
  preflight(d);need(not a.resources(m),'REMOTE_UNJOURNALED_RESOURCE_REFUSED')
  return{'status':'PREPARED_NO_RUNTIME_RESOURCES','volumes':'PRESERVED'}
 return core.cleanup_recorded(d/JOURNAL,a.command,lambda:authorize(d,True))


def run_stage(directory,name,args,file=None,timeout=1800):
 d,m,frozen=existing(directory)
 stages={n:(scope,argv)for n,scope,argv in producer.deployment_plan(a.document(d/'frozen.compose.json'),True,m.get('primerConcurrency',1),static_manifest=m if m.get('staticTopology') else None,platform_verification=bool(m.get('platformStartup')))}
 need(name in stages and stages[name]==('compose',args),'REMOTE_SOURCE_STAGE_CHANGED')
 values=list(args);action='run'if'run'in values else values[0];i=values.index(action);role_index=next(n for n in range(i+1,len(values))if values[n]in frozen['epochs']['candidate']['layouts'])
 roles=[values[role_index]]if action=='run'else values[role_index:];options=values[i+1:role_index]
 expected_prefix=core.prefix(frozen['project'],frozen['envFile'],frozen['epochs']['candidate']['configFile'])
 def runner(argv):
  mutating=argv[:len(expected_prefix)]==expected_prefix and core.mutation(argv[len(expected_prefix):])
  return a.command(argv,file=file if mutating else None,timeout=timeout if mutating else 120)
 return core.checked_run(frozen,action,roles,runner,lambda:authorize(d),d/JOURNAL,options=options,stage=name if action=='run'else None)

def restart(directory,roles,at):
 d,m,frozen=existing(directory);journal=a.document(d/JOURNAL);records=[r for r in journal['records'].values()if r['service']in roles]
 need(len(records)==len(roles)and{r['service']for r in records}==set(roles),'REMOTE_RESTART_EXACT_ROSTER')
 core.checked_ids(d/JOURNAL,'restart',[r['id']for r in records],a.command,lambda:authorize(d));starts={}
 for r in records:
  row=json.loads(a.command(['docker','inspect',r['id']]))[0];state=row['State'];started=core._created_seconds(state['StartedAt'])*1000
  need(row['Id']==r['id']and state['Running']is True and started>=at,'REMOTE_RESTART_NOT_OBSERVED')
  starts[r['service']]={'startedAt':state['StartedAt'],'pid':state['Pid']}
 return{'commandMs':int(time.time()*1000)-at,'starts':starts}
