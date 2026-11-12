import copy,hashlib,importlib.util,json,pathlib,sys
sys.dont_write_bytecode=True
root=pathlib.Path(sys.argv[1]);raw=pathlib.Path(sys.argv[2]);sys.path.insert(0,str(root/'tools/mt-bench/m7-joined'))
import evaluator_progress as p
x=json.loads(raw.read_bytes());proof=x['proof'];services=sorted(x['containers']);rows,ids=p.decode_rounds(proof,2,services)
assert p.verify(proof,2,services,'idle')==x['result']
checks=[]
def check(name,change,expected):
 v=copy.deepcopy(proof);change(v)
 try:p.verify(v,2,services,'idle')
 except p.Refused as e:
  assert str(e)==expected,(name,str(e));checks.append({'control':name,'verdict':e.verdict,'code':str(e)})
 else:raise AssertionError(name+' FALSE_PASS')
 assert p.verify(proof,2,services,'idle')==x['result']
def column(v,key,condition,value):
 n=v['columns'].index(key)
 for r in v['rounds']:
  for row in r['rows']:
   if condition(row):row[n]=value(row,r)
owner=next(row for row in proof['rounds'][0]['rows'] if row[8]);foreign=next(row for row in proof['rounds'][0]['rows'] if not row[8])
check('stalled-owner',lambda v:column(v,'completedTimeCycles',lambda row:row[:2]==owner[:2],lambda row,r:owner[4]),'M7_EVALUATOR_PROGRESS_NOT_OBSERVED')
check('hidden-failure',lambda v:v['rounds'][-1]['rows'][1].__setitem__(5,1),'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE')
check('foreign-work',lambda v:v['rounds'][-1]['rows'][0].__setitem__(4,foreign[4]+1),'M7_EVALUATOR_PROGRESS_FOREIGN')
check('missing-foreign',lambda v:v['rounds'][-1]['rows'].pop(),'M7_EVALUATOR_PROGRESS_COVERAGE')
check('runtime-reset',lambda v:v['rounds'][-1]['instances']['evaluator'].__setitem__('runtimeId','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),'M7_EVALUATOR_PROGRESS_RESET')
check('generation-reset',lambda v:v['rounds'][-1]['rows'][1].__setitem__(2,999),'M7_EVALUATOR_PROGRESS_RESET')
check('invalid-due',lambda v:v['rounds'][-1]['rows'][1].__setitem__(12,True),'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
spec=importlib.util.spec_from_file_location('gate',root/'tools/queue/gates/m7_joined_receipt.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
expected={'nativeEvaluatorTimeWitness':{'artifact':{'path':'observation.private.json','sha256':hashlib.sha256(raw.read_bytes()).hexdigest()},'attribution':{'core':x['source'],'deploy':x['binding'],'imageId':x['imageId'],'instrument':x['instrumentSha256']},'tenants':2,'services':services,'proofPointer':'/proof'}}
class Evidence:
 def __init__(self,doc):self.doc=doc
 def json(self,ref):assert ref==expected['nativeEvaluatorTimeWitness']['artifact'];return self.doc
assert g.native_time_witness(expected,Evidence(x))==x['result']
for name,mutate,code in [('wrong-image',lambda d:d.__setitem__('imageId','sha256:'+'0'*64),'M7_NATIVE_EVALUATOR_TIME_IDENTITY'),('historical-downgrade',lambda d:d['proof'].update(kind='evaluator-progress-phase-v1',policy=p.LEGACY_POLICY),'M7_NATIVE_EVALUATOR_TIME_VERSION')]:
 d=copy.deepcopy(x);mutate(d)
 try:g.native_time_witness(expected,Evidence(d))
 except ValueError as e:assert str(e)==code;checks.append({'control':name,'verdict':'REFUSED','code':str(e)})
 else:raise AssertionError(name+' FALSE_PASS')
 assert g.native_time_witness(expected,Evidence(x))==x['result']
print(json.dumps({'restored':'PASS','negativeControls':checks,'nativeExpectation':expected},indent=2))
