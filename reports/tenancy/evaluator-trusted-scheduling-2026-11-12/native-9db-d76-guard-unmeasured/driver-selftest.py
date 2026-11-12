"""Recording-only final driver controls; no native project or Docker access."""
import importlib.util,json,pathlib,shutil,types,contextlib,io,uuid
here=pathlib.Path(__file__).parent
specification=importlib.util.spec_from_file_location('owned_final_capture',here/'capture.py');driver=importlib.util.module_from_spec(specification);specification.loader.exec_module(driver)
base=pathlib.Path('/tmp/ns-api-native-9db-finalguard-driver-test-20261112');base.mkdir(mode=0o700)
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';services=['evaluator','evaluator-2','evaluator-3'];image='sha256:'+'a'*64;calls=[];zero=False
s={'source':'9db0ce94f072c8f34aab889f0181afa4269a6758','binding':'d76ef17878edb610cdeae75aeef9c07f94b60753','imageId':image,'nonce':str(uuid.uuid4()),'project':'ns-evaluator-binding-proof-20261112-guard','secondsBetween':10,'ids':[A,B],'composeArgs':['compose'],'containers':{service:{'id':str(i)*64,'startedAt':'synthetic-only'} for i,service in enumerate(services,1)}}
pair={'org.opencontainers.image.revision':s['source'],'org.nightscout.deploy.revision':s['binding']}
def check(argv,**kw):
 if argv[0]=='git':return driver.INSTRUMENT_COMMIT+'\n'
 if argv[1]=='image':return json.dumps(pair)
 service=next(name for name,row in s['containers'].items() if row['id']==argv[-1]);row=s['containers'][service]
 return ' '.join(json.dumps(v) for v in (row['id'],image,row['startedAt'],True,{'com.docker.compose.project':s['project'],'com.docker.compose.service':service}))
def run(argv,**kw):
 service=argv[argv.index('-T')+1];step=len(calls)//3;calls.append(service);ordinal=services.index(service)
 rows=[]
 for tenant,owner in [(A,1),(B,0)]:
  admitted=owner==ordinal;count=step if admitted and not zero else 0
  rows.append({'tenant':tenant,'admitted':admitted,'ready':admitted,'code':None,'cycles':1+count if admitted else 0,'evaluation':{'alert':None},'dueAt':1 if admitted else None,'dueReason':'slow' if admitted else None,'jobs':dict.fromkeys(['running','booting','acquire','time','parentAcquire','parentTime'],False),'progress':{'generation':owner+1,'completedAcquisitions':1 if admitted else 0,'completedTimeCycles':count,'failedCompletions':0,'lastCompletedAgeMs':0 if admitted else None}})
 page={'selected':[A,B],'selfOrdinal':ordinal,'selfMode':'partitioned','observedAt':driver.time.time_ns()//1000000,'view':{'kind':'evaluator','runtimeId':str(ordinal+3)*8+'-1111-4111-8111-111111111111','configured':{'ordinal':ordinal,'mode':'partitioned'},'gate':{'eligible':True,'reason':None},'tenants':rows}}
 return types.SimpleNamespace(returncode=0,stdout=(json.dumps(page)+'\n').encode(),stderr=b'')
def select(name):
 root=base/name;root.mkdir();driver.HERE=root;shutil.copyfile(here/'instrument-manifest.json',root/'instrument-manifest.json');marker=root/'owned.json';marker.write_text(json.dumps({'nonce':s['nonce']}));marker.chmod(0o600);s['ownedPairFile']=str(marker);s['ownedPairSha256']=driver.hashlib.sha256(marker.read_bytes()).hexdigest();driver.EXPECTED_PAIR_FILE=marker;calls.clear()
driver.subprocess.check_output=check;driver.subprocess.run=run;driver.time.sleep=lambda _:None
with contextlib.redirect_stdout(io.StringIO()):
 select('positive');driver.main(s);assert len(calls)==9
 value=json.loads((driver.HERE/'strict-time/observation.private.json').read_text());assert value['kind']=='native-bounded-evaluator-due-listener-qualification' and value['proof']['kind']=='evaluator-progress-phase-v2' and value['result']['completedTimeDelta']==4
 before=len(calls)
 try:driver.main(s);raise AssertionError('EXACT_ONCE_GUARD_MISSING')
 except FileExistsError:pass
 assert len(calls)==before
 old=s['nonce'];s['nonce']=str(uuid.uuid4())
 try:driver.main(s);raise AssertionError('NONCE_GUARD_MISSING')
 except driver.p.Refused as error:assert str(error)=='NATIVE_FRESH_NONCE_PIN'
 s['nonce']=old;assert len(calls)==before
 zero=True;select('zero-work')
 try:driver.main(s);raise AssertionError('ZERO_WORK_FALSE_PASS')
 except driver.p.Refused as error:assert str(error)=='M7_EVALUATOR_PROGRESS_NOT_OBSERVED'
 assert len(calls)==9 and json.loads((driver.HERE/'strict-time/observation.private.json').read_text())['result']['verdict']=='UNMEASURED'
print('RECORDING_ONLY: strictv2positive9fakeRPC; zero-work9fakeRPCrefused; exact-once+wrong-nonce prevent moreRPC. No native result.')
