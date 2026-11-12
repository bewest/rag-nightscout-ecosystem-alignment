"""Recording-only driver control: no Docker/subprocess/server is executed."""
import importlib.util,json,pathlib,shutil,time,types,contextlib,io,uuid
here=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('owned_capture',here/'capture.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
root=pathlib.Path('<private-capture-prefix>-driver-test-final-20261112');root.mkdir(mode=0o700);driver.HERE=root
shutil.copyfile(here/'instrument-manifest.json',root/'instrument-manifest.json')
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
services=['evaluator','evaluator-2','evaluator-3'];image='sha256:'+'a'*64;nonce=str(uuid.uuid4())
marker=root/'owned.json';marker.write_text(json.dumps({'nonce':nonce}));marker.chmod(0o600)
s={'source':'2d0ae0354a38b4a88f43bc2ae5ec60c085058f64','binding':'dcc4a70bafd4edf31c5cab4bf3099883bd7e37f9','imageId':image,'nonce':nonce,'ownedPairFile':str(marker),'ownedPairSha256':driver.hashlib.sha256(marker.read_bytes()).hexdigest(),'project':'recording-only','secondsBetween':10,'ids':[A,B],'composeArgs':['compose'],'containers':{service:{'id':str(i)*64,'startedAt':'synthetic-only'} for i,service in enumerate(services,1)}}
pair={'org.opencontainers.image.revision':s['source'],'org.nightscout.deploy.revision':s['binding']}
def check(argv,**kw):
 if argv[0]=='git':return driver.INSTRUMENT_COMMIT+'\n'
 if argv[1]=='image':return json.dumps(pair)
 service=next(name for name,row in s['containers'].items() if row['id']==argv[-1]);row=s['containers'][service]
 return ' '.join(json.dumps(v) for v in (row['id'],image,row['startedAt'],True,{'com.docker.compose.project':s['project'],'com.docker.compose.service':service}))
calls=[]
def run(argv,**kw):
 service=argv[argv.index('-T')+1];step=len(calls)//3;calls.append(service);ordinal=services.index(service)
 rows=[]
 for tenant,owner in [(A,1),(B,0)]:
  admitted=owner==ordinal;time_count=step if admitted and s['window']=='post-clinical-time' else 0
  rows.append({'tenant':tenant,'admitted':admitted,'ready':admitted,'code':None,'cycles':1+time_count if admitted else 0,'evaluation':{'alert':None},'dueAt':0 if admitted and step<2 and s['window']=='post-clinical-time' else time.time()*1000+600000 if admitted else None,'dueReason':'slow' if admitted else None,'jobs':dict.fromkeys(driver.idle.FLAGS,False),'progress':{'generation':owner+1,'completedAcquisitions':1 if admitted else 0,'completedTimeCycles':time_count,'failedCompletions':0,'lastCompletedAgeMs':0 if admitted else None}})
 page={'selected':[A,B],'selfOrdinal':ordinal,'selfMode':'partitioned','observedAt':time.time_ns()//1000000,'view':{'kind':'evaluator','runtimeId':str(ordinal+3)*8+'-1111-4111-8111-111111111111','configured':{'ordinal':ordinal,'mode':'partitioned'},'gate':{'eligible':True,'reason':None},'tenants':rows}}
 return types.SimpleNamespace(returncode=0,stdout=(json.dumps(page)+'\n').encode(),stderr=b'')
driver.subprocess.check_output=check;driver.subprocess.run=run;driver.time.sleep=lambda _:None
with contextlib.redirect_stdout(io.StringIO()):
 for window in ('default-idle','post-clinical-time'):
  s['window']=window;calls.clear();driver.main(s);assert len(calls)==9
  result=json.loads((root/window/'observation.private.json').read_text())['result'];assert result['verdict']=='PASS'
  if window=='default-idle':assert result['timeWitness'] is False and result['completedTimeDelta']==0
  else:assert result['completedTimeDelta']==4
  before=len(calls)
  try:driver.main(s);raise AssertionError('EXACT_ONCE_GUARD_MISSING')
  except FileExistsError:pass
  assert len(calls)==before
 saved=s['nonce'];s['nonce']=str(uuid.uuid4())
 try:driver.main(s);raise AssertionError('NONCE_GUARD_MISSING')
 except driver.p.Refused as error:assert str(error)=='NATIVE_FRESH_NONCE_PIN'
 s['nonce']=saved;assert len(calls)==before
print('RECORDING_ONLY: both branches9fakeRPCs; exact-once guard prevents additional fakeRPCs. No native result.')
