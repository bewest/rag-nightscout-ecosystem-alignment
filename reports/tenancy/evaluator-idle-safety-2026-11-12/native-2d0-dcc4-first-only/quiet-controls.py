"""Actual captured idle rows only; offline mutations, no resource access."""
import copy,hashlib,json,pathlib,sys
sys.dont_write_bytecode=True
BASE=pathlib.Path(__file__).parent
sys.path.insert(0,str(BASE/'instrument-c33/tools/mt-bench/m7-joined'))
import evaluator_idle as idle
import evaluator_progress as p
raw=(BASE/'default-idle/observation.private.json').read_bytes();capture=json.loads(raw);proof=capture['proof'];services=sorted(capture['containers']);columns=proof['columns']
result=idle.verify(proof,2,services);assert result==capture['result']
def owner(value,step=1):return next(row for row in value['rounds'][step]['rows'] if row[columns.index('admitted')])
def foreign(value,step=1):return next(row for row in value['rounds'][step]['rows'] if not row[columns.index('admitted')])
controls=[]
def check(name,mutate,code,verdict='UNMEASURED'):
 value=copy.deepcopy(proof);mutate(value)
 try:idle.verify(value,2,services);raise AssertionError('MUTATION_FALSE_PASS_'+name)
 except p.Refused as error:assert code in str(error) and error.verdict==verdict;(controls.append({'name':name,'verdict':error.verdict,'code':str(error)}))
 assert idle.verify(proof,2,services)==result
for bit,flag in enumerate(idle.FLAGS):check('clinical-'+flag,lambda v,bit=bit:owner(v).__setitem__(columns.index('jobs'),1<<bit),'JOB_PENDING')
check('legacy-only-work',lambda v:owner(v,2).__setitem__(columns.index('legacyCycles'),2),'UNCREDITED_WORK')
check('earlier-due-cannot-be-hidden',lambda v:owner(v,0).__setitem__(columns.index('dueAt'),v['rounds'][0]['readStartedAtMs']),'TIME_NOT_OBSERVED')
check('hidden-failure',lambda v:owner(v).__setitem__(columns.index('failedCompletions'),1),'HIDDEN_FAILURE','FAIL')
check('foreign-work',lambda v:foreign(v).__setitem__(columns.index('legacyCycles'),1),'FOREIGN','FAIL')
check('runtime-reset',lambda v:v['rounds'][1]['instances'][services[0]].__setitem__('runtimeId','ffffffff-ffff-4fff-8fff-ffffffffffff'),'RESET','FAIL')
check('missing-foreign-row',lambda v:v['rounds'][1]['rows'].remove(foreign(v)),'COVERAGE','FAIL')
check('boolean-job-mask',lambda v:owner(v).__setitem__(columns.index('jobs'),False),'IDLE_JOBS')
check('missing-current-job-column',lambda v:v.__setitem__('columns',list(p.COLUMNS)),'IDLE_VERSION')
check('missing-read-stamps',lambda v:v['rounds'][1].pop('readWindows'),'IDLE_CLOCK')
check('wall-clock-jump',lambda v:v['rounds'][2]['readWindows'][services[0]]['end'].__setitem__('wallUs',v['rounds'][2]['readWindows'][services[0]]['end']['wallUs']+1000000),'IDLE_CLOCK')
# The actual zero-work capture cannot become a strict TIME witness by retagging.
strict=copy.deepcopy(proof);strict.update(kind='evaluator-progress-phase-v2',columns=list(p.COLUMNS),policy=p.POLICY,version=2)
for value in strict['rounds']:value['rows']=[row[:-1] for row in value['rows']]
try:p.verify(strict,2,services,'idle');raise AssertionError('QUIET_FALSE_TIME_WITNESS')
except p.Refused as error:assert 'NOT_OBSERVED' in str(error);controls.append({'name':'quiet-is-not-strict-time','verdict':error.verdict,'code':str(error)})
rows=[]
for index,round in enumerate(proof['rounds']):
 for packed in round['rows']:
  row=dict(zip(columns,packed));window=round['readWindows'][row['service']]
  rows.append({'round':index,**row,'readStartUs':window['start']['wallUs'],'readEndUs':window['end']['wallUs'],'helperObservedAtMs':window['observedAt']})
summary={'scope':'OFFLINE actual first idle capture only; no live stopped-worker control','rawSha256':hashlib.sha256(raw).hexdigest(),'recomputed':result,'rows':rows,'controls':controls,'restored':'PASS'}
file=BASE/'default-idle/classification.private.json';file.write_text(json.dumps(summary,separators=(',',':'))+'\n');file.chmod(0o600)
print(json.dumps({'recomputed':result['verdict'],'controls':len(controls),'restored':'PASS','strictTimeFromQuiet':'UNMEASURED','rowsRetained':len(rows)}))
