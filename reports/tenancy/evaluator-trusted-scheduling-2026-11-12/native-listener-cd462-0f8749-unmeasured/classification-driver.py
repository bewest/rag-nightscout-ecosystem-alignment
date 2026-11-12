"""Offline classification; never queries a stack or changes a measured value."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,'<alignment>/externals/work/alignment-m7-evaluator-progress-20261112/tools/mt-bench/m7-joined')
import evaluator_progress as p
r=Path(__file__).parent;value=json.loads((r/'observation.private.json').read_text());proof=value['proof'];services=sorted(value['containers'])
def recompute(record):
 rounds,ids=p.decode_rounds(record,2,services)
 return p.assess(rounds,sorted(ids),'idle')
try:recompute(proof)
except p.Refused as error:
 assert error.verdict=='UNMEASURED' and str(error)=='M7_EVALUATOR_PROGRESS_NOT_OBSERVED'
else:raise AssertionError('UNEXPECTED_PASS')
rounds,ids=p.decode_rounds(proof,2,services);base,last=rounds[0],rounds[-1]
per=[]
for tenant in sorted(ids):
 a,b=base['owners'][tenant],last['owners'][tenant]
 per.append({'tenant':tenant,'service':a['service'],'runtimeId':a['runtimeId'],'generation':a['generation'],'baseline':{k:a[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles','lastCompletedAgeMs')},'end':{k:b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles','lastCompletedAgeMs')},'completedAcquisitionDelta':b['completedAcquisitions']-a['completedAcquisitions'],'completedTimeDelta':b['completedTimeCycles']-a['completedTimeCycles'],'failedDelta':b['failedCompletions']-a['failedCompletions']})
controls=[]
for mode in ('hidden-failure','foreign-work','runtime-reset','missing-foreign-row','unmeasured-wrapped-as-pass'):
 broken=copy.deepcopy(proof)
 if mode=='unmeasured-wrapped-as-pass':broken.update(policy=p.POLICY,verdict='PASS',phase='idle')
 elif mode=='runtime-reset':broken['rounds'][-1]['instances'][services[0]]['runtimeId']='99999999-9999-4999-8999-999999999999'
 else:
  rows=broken['rounds'][-1]['rows'];admitted=p.COLUMNS.index('admitted')
  row=next(v for v in rows if v[admitted]) if mode=='hidden-failure' else next(v for v in rows if not v[admitted])
  if mode=='missing-foreign-row':rows.remove(row)
  else:row[p.COLUMNS.index('failedCompletions' if mode=='hidden-failure' else 'completedTimeCycles')]+=1
 try:p.verify(broken,2,services,'idle') if mode=='unmeasured-wrapped-as-pass' else recompute(broken)
 except p.Refused as error:controls.append({'control':mode,'verdict':error.verdict,'code':str(error)})
 else:raise AssertionError('CONTROL_FALSE_PASS '+mode)
commands=[json.loads(f.read_text()) for f in r.glob('*.command.json')]
raw=(r/'observation.private.json').read_bytes();compressed=(r/'observation.private.json.gz').read_bytes();assert gzip.decompress(compressed)==raw
out={'source':value['source'],'binding':value['binding'],'imageId':value['imageId'],'verdict':'UNMEASURED','code':'M7_EVALUATOR_PROGRESS_NOT_OBSERVED','elapsedSeconds':value['elapsedSeconds'],'calls':len(commands),'successfulCalls':sum(v['returncode']==0 for v in commands),'responseBytes':sum(v['bytes'] for v in commands),'collectorParallelWallSeconds':sum(v['wallSeconds'] for v in rounds),'sumPerInstanceExecWallSeconds':sum(v['wallSeconds'] for v in commands),'rowsPerRound':[len(v['rows']) for v in proof['rounds']],'foreignRowsPerRound':[sum(not row[p.COLUMNS.index('admitted')] for row in v['rows']) for v in proof['rounds']],'perTenant':per,'evaluatorDueState':'UNMEASURED; source runtime fields omitted by captured module-v2 DTO','controls':controls,'restored':'UNMEASURED/NOT_OBSERVED','rawSha256':hashlib.sha256(raw).hexdigest(),'gzipSha256':hashlib.sha256(compressed).hexdigest()}
(r/'classification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
