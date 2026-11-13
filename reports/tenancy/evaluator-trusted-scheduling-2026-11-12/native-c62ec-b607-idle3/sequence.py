import pathlib,subprocess,json,os,time,hashlib,sys
from owned_process import run as run_owned
from episode_order import execute
H=pathlib.Path(__file__).parent;STATE=pathlib.Path('/tmp/ns-evaluator-binding-proof-20261112-guard');DEADLINE=json.loads((H/'activation-deadline.json').read_text())['deadlineMonotonic'];r={'kind':'final-collector-native-sequence','startedAtMs':time.time_ns()//1000000,'phases':{}}
def save():(H/'sequence-processes.private.json').write_text(json.dumps(r,indent=2)+'\n')
def call(name,argv,timeout=90):
 row={'startedAtMs':time.time_ns()//1000000,'argv':argv};r['phases'][name]=row;save()
 with (H/(name+'.phase.stdout.log')).open('xb')as out:result=run_owned(argv,out,timeout if name.startswith('stop-retain')else min(timeout,max(.1,DEADLINE-time.monotonic()-5)))
 row.update(result);save()
 if result['timedOut']:raise TimeoutError('OWNED_PHASE_TIMEOUT_UNMEASURED')
 assert result['returnCode']==0,name
def observe():
  episode=json.loads((H/'episode/episode.json').read_text());assert episode['outcome']=='opportunity-established'
  pins=json.loads(pathlib.Path('/tmp/ns-api-native-9db-pair-20261112/fresh-ingestion/expected-release-pins.json').read_text());pins.update(instrumentCommit=json.loads((H/'freeze.json').read_text())['commit'],instrumentSha256=json.loads((H/'freeze.json').read_text())['sha256'],phase='ROOT_FINAL_COLLECTOR_FRESH_RELEASED',experiment='idle-assessor3 current instrument fresh native TIME episode; old captures unchanged');(H/'expected-release-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
  call('select-current-spec',[sys.executable,str(H/'select-spec.py'),'--release','root-final-collector-fresh-ingestion-time'],45)
  call('strict-time',[sys.executable,str(H/'run-once.py')],90)
try:
 execute(lambda:call('startup-settlement',[sys.executable,str(H/'settlement.py')],15),lambda:call('readiness',[sys.executable,str(H/'ready.py')],100),lambda:call('fresh-ingestion',[sys.executable,str(H/'episode/run.py')],45),observe)
 r['outcome']='PASS'
except Exception as error:r['outcome']='STOPPED_FAILURE';r['failureType']=type(error).__name__;save();raise
finally:
 old=json.loads((STATE/'artifacts/retained-final-stop.private.json').read_text());ids=[c['Id']for c in old['after']];expected={c['Id']:c for c in old['after']};before=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True));assert len(before)==15
 for c in before:assert c['Image']==expected[c['Id']]['Image']and c['Config']['Labels']==expected[c['Id']]['Config']['Labels']
 call('stop-retain-final15',['docker','stop','--time','20',*ids],45)
 after=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True));assert all(not c['State']['Running']and c['State']['Status']=='exited'for c in after)
 def canon(x):
  if isinstance(x,list):return sorted([canon(v)for v in x],key=lambda v:json.dumps(v,sort_keys=True))
  if isinstance(x,dict):return{k:canon(x[k])for k in sorted(x)}
  return x
 for c in after:assert c['Image']==expected[c['Id']]['Image']and c['Config']['Labels']==expected[c['Id']]['Config']['Labels']and canon(c['Mounts'])==canon(expected[c['Id']]['Mounts'])
 (H/'stopped-custody.private.json').write_text(json.dumps({'before':before,'after':after,'retained15':True},indent=2)+'\n');r.update(stoppedRetained15=True,finishedAtMs=time.time_ns()//1000000);save();print(json.dumps({k:v for k,v in r.items()if k!='phases'}))
