"""Offline actual-UM classification and corruption controls; never invent progress."""
import copy,hashlib,importlib.util,json,pathlib,sys
sys.dont_write_bytecode=True;archive=pathlib.Path(sys.argv[1]);raw=pathlib.Path(sys.argv[2]);sys.path.insert(0,str(archive/'tools/mt-bench/m7-joined'));import evaluator_progress as p
x=json.loads(raw.read_bytes());services=sorted(x['containers']);proof=x['proof']
def classify(v):
 rounds,ids=p.decode_rounds(v,2,services)
 try:p.assess(rounds,sorted(ids),'idle')
 except p.Refused as e:return {'verdict':e.verdict,'code':str(e)}
 raise AssertionError('ACTUAL_PROGRESS_INVENTED')
assert classify(proof)==x['result']=={'verdict':'UNMEASURED','code':'M7_EVALUATOR_PROGRESS_NOT_OBSERVED'}
controls=[]
for name,change,expected in [('hidden-failure',lambda v:v['rounds'][-1]['rows'][1].__setitem__(5,1),'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE'),('foreign-work',lambda v:v['rounds'][-1]['rows'][0].__setitem__(4,3),'M7_EVALUATOR_PROGRESS_FOREIGN'),('runtime-reset',lambda v:v['rounds'][-1]['instances']['evaluator'].__setitem__('runtimeId','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),'M7_EVALUATOR_PROGRESS_RESET'),('missing-foreign',lambda v:v['rounds'][-1]['rows'].pop(),'M7_EVALUATOR_PROGRESS_COVERAGE'),('invalid-due',lambda v:v['rounds'][-1]['rows'][1].__setitem__(12,True),'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')]:
 v=copy.deepcopy(proof);change(v)
 try:observed=classify(v)
 except p.Refused as e:observed={'verdict':e.verdict,'code':str(e)}
 assert observed['code']==expected,(name,observed);controls.append({'control':name,**observed});assert classify(proof)==x['result']
spec=importlib.util.spec_from_file_location('gate',archive/'tools/queue/gates/m7_joined_receipt.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
pins={'core':x['source'],'deploy':x['binding'],'imageId':x['imageId'],'instrument':x['instrumentSha256']};expected={'nativeEvaluatorTimeWitness':{'artifact':{'path':raw.name,'sha256':hashlib.sha256(raw.read_bytes()).hexdigest()},'attribution':pins,'tenants':2,'services':services,'proofPointer':'/proof'}}
class Evidence:
 def json(self,reference):return x
try:g.native_time_witness(expected,Evidence())
except ValueError as e:native_refusal=str(e)
else:raise AssertionError('UM_NATIVE_WITNESS_FALSE_PASS')
print(json.dumps({'actualClassification':classify(proof),'restoredClassification':'UNMEASURED','corruptionControls':controls,'currentNativeGateRefusal':native_refusal,'attemptedNativeExpectationNOTacceptedWitness':expected},indent=2))
